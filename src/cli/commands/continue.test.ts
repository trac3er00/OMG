import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { mkdirSync, rmSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createPauseCheckpoint } from "./pause.js";
import { findLatestCheckpoint, restoreFromCheckpoint } from "./continue.js";

describe("continue command", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "omg-continue-test-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("returns null when no checkpoint exists", () => {
    expect(findLatestCheckpoint(tmpDir)).toBeNull();
  });

  it("finds checkpoint after pause", () => {
    createPauseCheckpoint(tmpDir);
    expect(findLatestCheckpoint(tmpDir)).not.toBeNull();
  });

  it("restores from valid checkpoint", () => {
    createPauseCheckpoint(tmpDir);
    const result = restoreFromCheckpoint(tmpDir);
    expect(result.success).toBe(true);
    expect(result.message).toContain("Restored");
  });

  it("rejects stale checkpoint", () => {
    const stateDir = join(tmpDir, ".omg", "state");
    mkdirSync(stateDir, { recursive: true });
    const stale = JSON.stringify({
      session_id: "stale-test",
      timestamp: "2020-01-01T00:00:00.000Z",
      version: "2.3.0",
      pending_tasks: [],
      memory_snapshot: {},
      context_summary: "",
      provider: "unknown",
    });
    writeFileSync(join(stateDir, "checkpoint-stale-test.json"), stale);
    const result = restoreFromCheckpoint(tmpDir);
    expect(result.success).toBe(false);
    expect(result.message).toContain("stale");
  });

  it("rejects version-incompatible checkpoint", () => {
    const stateDir = join(tmpDir, ".omg", "state");
    mkdirSync(stateDir, { recursive: true });
    const incompatible = JSON.stringify({
      session_id: "incompat-test",
      timestamp: new Date().toISOString(),
      version: "1.0.0",
      pending_tasks: [],
      memory_snapshot: {},
      context_summary: "",
      provider: "unknown",
    });
    writeFileSync(
      join(stateDir, "checkpoint-incompat-test.json"),
      incompatible,
    );
    const result = restoreFromCheckpoint(tmpDir);
    expect(result.success).toBe(false);
    expect(result.message).toContain("mismatch");
  });
});
