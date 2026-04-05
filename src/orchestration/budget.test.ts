import { describe, expect, test } from "bun:test";

import { BudgetEnvelope } from "./budget.js";

describe("BudgetEnvelope.create", () => {
  test("creates envelope with specified limits", () => {
    const env = BudgetEnvelope.create("run-1", { tokens: 1000 });
    expect(env.runId).toBe("run-1");
    expect(env.remaining("tokens")).toBe(1000);
  });

  test("uncapped dimension returns Infinity remaining", () => {
    const env = BudgetEnvelope.create("run-2", { tokens: 500 });
    expect(env.remaining("cpu_ms")).toBe(Infinity);
  });

  test("all dimensions start at zero usage", () => {
    const env = BudgetEnvelope.create("run-3", {
      tokens: 1000,
      cpu_ms: 5000,
      memory_mb: 256,
    });
    expect(env.used("tokens")).toBe(0);
    expect(env.used("cpu_ms")).toBe(0);
    expect(env.used("memory_mb")).toBe(0);
  });
});

describe("BudgetEnvelope.record", () => {
  test("additive recording for tokens", () => {
    const env = BudgetEnvelope.create("run-4", { tokens: 1000 });
    env.record("tokens", 200);
    env.record("tokens", 300);
    expect(env.used("tokens")).toBe(500);
    expect(env.remaining("tokens")).toBe(500);
  });

  test("additive recording for cpu_ms", () => {
    const env = BudgetEnvelope.create("run-5", { cpu_ms: 10000 });
    env.record("cpu_ms", 3000);
    env.record("cpu_ms", 2000);
    expect(env.used("cpu_ms")).toBe(5000);
  });

  test("memory_mb tracks peak (max) not sum", () => {
    const env = BudgetEnvelope.create("run-6", { memory_mb: 512 });
    env.record("memory_mb", 100);
    env.record("memory_mb", 300);
    env.record("memory_mb", 200);
    expect(env.used("memory_mb")).toBe(300);
  });
});

describe("BudgetEnvelope.check", () => {
  test("under budget → not exceeded", () => {
    const env = BudgetEnvelope.create("run-7", { tokens: 1000 });
    env.record("tokens", 900);
    const result = env.check();
    expect(result.exceeded).toBe(false);
    expect(result.dimensions).toEqual([]);
  });

  test("at limit → exceeded", () => {
    const env = BudgetEnvelope.create("run-8", { tokens: 1000 });
    env.record("tokens", 1000);
    const result = env.check();
    expect(result.exceeded).toBe(true);
    expect(result.dimensions).toContain("tokens");
  });

  test("over budget → exceeded with dimension list", () => {
    const env = BudgetEnvelope.create("run-9", { tokens: 1000 });
    env.record("tokens", 900);
    env.record("tokens", 200);
    const result = env.check();
    expect(result.exceeded).toBe(true);
    expect(result.dimensions).toContain("tokens");
  });

  test("multiple dimensions can exceed independently", () => {
    const env = BudgetEnvelope.create("run-10", {
      tokens: 100,
      cpu_ms: 500,
    });
    env.record("tokens", 150);
    env.record("cpu_ms", 200);
    const result = env.check();
    expect(result.exceeded).toBe(true);
    expect(result.dimensions).toContain("tokens");
    expect(result.dimensions).not.toContain("cpu_ms");
  });

  test("uncapped dimensions never exceed", () => {
    const env = BudgetEnvelope.create("run-11", { tokens: 1000 });
    env.record("cpu_ms", 999999);
    const result = env.check();
    expect(result.exceeded).toBe(false);
  });
});

describe("BudgetEnvelope.remaining", () => {
  test("returns correct remaining after recording", () => {
    const env = BudgetEnvelope.create("run-12", { tokens: 1000 });
    env.record("tokens", 750);
    expect(env.remaining("tokens")).toBe(250);
  });

  test("remaining floors at zero (no negatives)", () => {
    const env = BudgetEnvelope.create("run-13", { tokens: 100 });
    env.record("tokens", 200);
    expect(env.remaining("tokens")).toBe(0);
  });
});

describe("BudgetEnvelope.pressure", () => {
  test("pressure = used / limit", () => {
    const env = BudgetEnvelope.create("run-14", { tokens: 1000 });
    env.record("tokens", 500);
    expect(env.pressure("tokens")).toBe(0.5);
  });

  test("uncapped dimension has zero pressure", () => {
    const env = BudgetEnvelope.create("run-15", { tokens: 1000 });
    expect(env.pressure("cpu_ms")).toBe(0);
  });
});

describe("BudgetEnvelope.toSnapshot", () => {
  test("snapshot matches BudgetEnvelope interface", () => {
    const env = BudgetEnvelope.create("run-16", {
      tokens: 1000,
      cpu_ms: 5000,
      memory_mb: 256,
      wall_time_ms: 30000,
      network_bytes: 1048576,
    });
    env.record("tokens", 200);
    env.record("cpu_ms", 1000);

    const snap = env.toSnapshot();
    expect(snap.runId).toBe("run-16");
    expect(snap.tokenLimit).toBe(1000);
    expect(snap.tokensUsed).toBe(200);
    expect(snap.cpuSecondsLimit).toBe(5000);
    expect(snap.cpuSecondsUsed).toBe(1000);
    expect(snap.exceeded).toBe(false);
    expect(snap.exceededDimensions).toEqual([]);
  });

  test("snapshot reflects exceeded state", () => {
    const env = BudgetEnvelope.create("run-17", { tokens: 100 });
    env.record("tokens", 150);
    const snap = env.toSnapshot();
    expect(snap.exceeded).toBe(true);
    expect(snap.exceededDimensions).toContain("tokens");
  });
});

describe("QA Scenario: Budget limit enforcement", () => {
  test("create envelope → record under → check ok → record over → check exceeded", () => {
    const env = BudgetEnvelope.create("qa-run", { tokens: 1000 });

    env.record("tokens", 900);
    const first = env.check();
    expect(first.exceeded).toBe(false);

    env.record("tokens", 200);
    const second = env.check();
    expect(second.exceeded).toBe(true);
    expect(second.dimensions).toContain("tokens");
  });
});
