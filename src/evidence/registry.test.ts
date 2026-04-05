import { describe, test, expect } from "bun:test";
import { EvidenceRegistry } from "./registry.js";
import { EvidenceNarrator } from "./narrator.js";
import { EvidenceQuery } from "./query.js";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync } from "node:fs";

function mkRegistry(): {
  registry: EvidenceRegistry;
  narrator: EvidenceNarrator;
  query: EvidenceQuery;
  dir: string;
} {
  const dir = join(tmpdir(), `ev-reg-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const registry = new EvidenceRegistry(dir);
  return {
    registry,
    narrator: new EvidenceNarrator(),
    query: new EvidenceQuery(registry),
    dir,
  };
}

describe("EvidenceRegistry", () => {
  test("register and retrieve by type", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "run-001", path: "results.xml", valid: true });
      registry.register({ type: "coverage", runId: "run-001", path: "coverage.json", valid: true });
      const byType = registry.findByType("junit");
      expect(byType).toHaveLength(1);
      expect(byType[0]?.type).toBe("junit");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("findByRun returns all evidence for a run", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "run-A", path: "r.xml", valid: true });
      registry.register({ type: "sarif", runId: "run-A", path: "s.json", valid: true });
      registry.register({ type: "junit", runId: "run-B", path: "r2.xml", valid: true });
      const runAEvidence = registry.findByRun("run-A");
      expect(runAEvidence).toHaveLength(2);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("hasRequired returns true when required types present", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r", path: "r.xml", valid: true });
      registry.register({ type: "coverage", runId: "r", path: "c.json", valid: true });
      expect(registry.hasRequired(["junit", "coverage"])).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("hasRequired returns false when missing", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r", path: "r.xml", valid: true });
      expect(registry.hasRequired(["junit", "coverage"])).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("all returns every registered record", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r1", path: "a.xml", valid: true });
      registry.register({ type: "sarif", runId: "r2", path: "b.json", valid: false });
      expect(registry.all()).toHaveLength(2);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("persists across instances", () => {
    const dir = join(tmpdir(), `ev-persist-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    try {
      const reg1 = new EvidenceRegistry(dir);
      reg1.register({ type: "junit", runId: "r1", path: "a.xml", valid: true });

      const reg2 = new EvidenceRegistry(dir);
      expect(reg2.all()).toHaveLength(1);
      expect(reg2.all()[0]?.type).toBe("junit");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("register adds timestamp automatically", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r", path: "r.xml", valid: true });
      const records = registry.all();
      expect(records[0]?.timestamp).toBeDefined();
      expect(typeof records[0]?.timestamp).toBe("string");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("register preserves metadata", () => {
    const { registry, dir } = mkRegistry();
    try {
      registry.register({
        type: "junit",
        runId: "r",
        path: "r.xml",
        valid: true,
        metadata: { lines: 42, tool: "bun" },
      });
      const records = registry.all();
      expect(records[0]?.metadata).toEqual({ lines: 42, tool: "bun" });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("EvidenceNarrator", () => {
  test("generates narrative from evidence list", () => {
    const narrator = new EvidenceNarrator();
    const narrative = narrator.narrate([
      { type: "junit", runId: "r", path: "r.xml", valid: true, timestamp: new Date().toISOString() },
      { type: "coverage", runId: "r", path: "c.json", valid: true, timestamp: new Date().toISOString() },
    ]);
    expect(typeof narrative).toBe("string");
    expect(narrative.length).toBeGreaterThan(0);
    expect(narrative).toContain("junit");
  });

  test("returns empty message for no evidence", () => {
    const narrator = new EvidenceNarrator();
    const narrative = narrator.narrate([]);
    expect(narrative).toBe("No evidence available.");
  });

  test("groups by type and shows valid counts", () => {
    const narrator = new EvidenceNarrator();
    const narrative = narrator.narrate([
      { type: "junit", runId: "r", path: "a.xml", valid: true, timestamp: new Date().toISOString() },
      { type: "junit", runId: "r", path: "b.xml", valid: false, timestamp: new Date().toISOString() },
      { type: "coverage", runId: "r", path: "c.json", valid: true, timestamp: new Date().toISOString() },
    ]);
    expect(narrative).toContain("junit: 1/2 valid");
    expect(narrative).toContain("coverage: 1/1 valid");
  });

  test("narrateMissing reports missing items", () => {
    const narrator = new EvidenceNarrator();
    expect(narrator.narrateMissing(["tests", "build"])).toContain("tests");
    expect(narrator.narrateMissing(["tests", "build"])).toContain("build");
  });

  test("narrateMissing returns all-present for empty list", () => {
    const narrator = new EvidenceNarrator();
    expect(narrator.narrateMissing([])).toContain("All required evidence is present");
  });
});

describe("EvidenceQuery", () => {
  test("query by type returns matching", () => {
    const { registry, query, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r", path: "r.xml", valid: true });
      registry.register({ type: "sarif", runId: "r", path: "s.json", valid: true });
      const results = query.byType("junit");
      expect(results.length).toBeGreaterThan(0);
      expect(results.every((r) => r.type === "junit")).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("query by run returns matching", () => {
    const { registry, query, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "run-X", path: "r.xml", valid: true });
      registry.register({ type: "sarif", runId: "run-Y", path: "s.json", valid: true });
      const results = query.byRun("run-X");
      expect(results).toHaveLength(1);
      expect(results[0]?.runId).toBe("run-X");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("hasAll checks required types", () => {
    const { registry, query, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r", path: "r.xml", valid: true });
      registry.register({ type: "coverage", runId: "r", path: "c.json", valid: true });
      expect(query.hasAll(["junit", "coverage"])).toBe(true);
      expect(query.hasAll(["junit", "sarif"])).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("byDateRange filters by timestamp", () => {
    const { registry, query, dir } = mkRegistry();
    try {
      registry.register({ type: "junit", runId: "r1", path: "a.xml", valid: true });
      const now = new Date();
      const oneMinAgo = new Date(now.getTime() - 60_000);
      const results = query.byDateRange(oneMinAgo.toISOString(), now.toISOString());
      expect(results).toHaveLength(1);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
