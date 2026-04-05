import { describe, test, expect } from "bun:test";
import {
  defaultLayout,
  schemaVersions,
  normalizeRunId,
  generateRunId,
  createProvenance,
} from "./contracts.js";

describe("defaultLayout", () => {
  const REQUIRED_MODULES = [
    "verification_controller",
    "release_run_coordinator",
    "interaction_journal",
    "context_engine",
    "defense_state",
    "session_health",
    "council_verdicts",
    "rollback_manifest",
    "release_run",
  ] as const;

  test("returns paths for all 9 required modules", () => {
    const layout = defaultLayout("/test/project");
    for (const mod of REQUIRED_MODULES) {
      expect(layout[mod]).toBeDefined();
      expect(typeof layout[mod]).toBe("string");
    }
  });

  test("all paths are under .omg/state/", () => {
    const layout = defaultLayout("/test/project");
    for (const [, path] of Object.entries(layout)) {
      expect(path).toContain(".omg/state/");
    }
  });

  test("context_engine path ends with .json", () => {
    const layout = defaultLayout("/test/project");
    expect(layout.context_engine).toMatch(/\.json$/);
  });

  test("defense_state path ends with .json", () => {
    const layout = defaultLayout("/test/project");
    expect(layout.defense_state).toMatch(/\.json$/);
  });

  test("resolves relative project dir", () => {
    const layout = defaultLayout("./myproject");
    for (const [, path] of Object.entries(layout)) {
      expect(path.startsWith("/")).toBe(true);
    }
  });
});

describe("schemaVersions", () => {
  test("returns schema for all 9 modules", () => {
    const versions = schemaVersions();
    expect(Object.keys(versions)).toHaveLength(9);
  });

  test("all versions have module and version fields", () => {
    const versions = schemaVersions();
    for (const [name, schema] of Object.entries(versions)) {
      expect(schema.module).toBe(name);
      expect(typeof schema.version).toBe("number");
      expect(schema.version).toBeGreaterThan(0);
    }
  });

  test("context_engine is at version 3", () => {
    const versions = schemaVersions();
    expect(versions.context_engine?.version).toBe(3);
  });
});

describe("normalizeRunId", () => {
  test("passes through clean run ID", () => {
    const id = "omg-20240101-abc123";
    expect(normalizeRunId(id)).toBe(id);
  });

  test("lowercases and strips special chars", () => {
    const result = normalizeRunId("RUN/WITH/SLASHES");
    expect(result).not.toContain("/");
    expect(result).toBe(result.toLowerCase());
  });

  test("removes .. sequences", () => {
    const result = normalizeRunId("run/../evil");
    expect(result).not.toContain("..");
  });

  test("enforces max length", () => {
    const long = "a".repeat(200);
    expect(normalizeRunId(long).length).toBeLessThanOrEqual(128);
  });

  test("returns generated ID for empty input", () => {
    const result = normalizeRunId("");
    expect(result).toMatch(/^omg-/);
    expect(result.length).toBeGreaterThan(5);
  });
});

describe("generateRunId", () => {
  test("starts with omg-", () => {
    expect(generateRunId()).toMatch(/^omg-/);
  });

  test("two calls produce different IDs", () => {
    expect(generateRunId()).not.toBe(generateRunId());
  });

  test("uses only safe chars", () => {
    const id = generateRunId();
    expect(/^[a-z0-9-]+$/.test(id)).toBe(true);
  });
});

describe("createProvenance", () => {
  test("creates provenance record with correct fields", () => {
    const prov = createProvenance("omg-abc123", "defense_state", "write", "/path/to/file");
    expect(prov.runId).toBe("omg-abc123");
    expect(prov.module).toBe("defense_state");
    expect(prov.operation).toBe("write");
    expect(prov.path).toBe("/path/to/file");
    expect(prov.timestamp).toBeTruthy();
    expect(prov.schemaVersion).toBe(2);
  });
});
