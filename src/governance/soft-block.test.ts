import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { GovernanceGraphRuntime } from "./graph.js";

const TEST_DIR = "/tmp/omg-soft-block-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("governance/soft-block", () => {
  test("soft-block-default", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR);
    expect(runtime.getEnforcementMode()).toBe("soft-block");
  });

  test("override-available", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR, "default", "advisory");
    expect(runtime.getEnforcementMode()).toBe("advisory");

    const hardRuntime = new GovernanceGraphRuntime(
      TEST_DIR,
      "default",
      "hard-block",
    );
    expect(hardRuntime.getEnforcementMode()).toBe("hard-block");
  });

  test("advisory-still-works", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR, "default", "advisory");
    expect(runtime.getEnforcementMode()).toBe("advisory");

    runtime.addNode("agent-a");
    runtime.addNode("agent-b");
    const result = runtime.validateAgentCombination(["agent-a", "agent-b"]);
    expect(result.mode).toBe("advisory");
    expect(result.allowed).toBe(true);
  });

  test("dot-export-unchanged", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR);
    runtime.addNode("task-1", "planning");
    runtime.addNode("task-2", "implementing");
    runtime.addEdge("task-1", "task-2");

    const dot = runtime.exportToDOT();
    expect(dot).toContain("digraph governance {");
    expect(dot).toContain("task-1");
    expect(dot).toContain("task-2");
    expect(dot).toContain("dependency");
    expect(dot).toContain("}");
  });

  test("soft-block-validation-returns-mode", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR);
    runtime.addNode("agent-x");
    const result = runtime.validateAgentCombination(["agent-x"]);
    expect(result.mode).toBe("soft-block");
    expect(result.allowed).toBe(true);
  });

  test("blocked-agent-detected-in-soft-block", () => {
    const runtime = new GovernanceGraphRuntime(TEST_DIR);
    runtime.addNode("agent-blocked", "blocked" as never);
    const result = runtime.validateAgentCombination(["agent-blocked"]);
    expect(result.allowed).toBe(false);
    expect(result.violations.length).toBeGreaterThan(0);
    expect(result.mode).toBe("soft-block");
  });
});
