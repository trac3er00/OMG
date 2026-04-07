import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createPauseCheckpoint, CheckpointSchema } from "./pause.js";

describe("pause command", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "omg-pause-test-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("creates checkpoint file with valid JSON", () => {
    const filename = createPauseCheckpoint(tmpDir);
    const content = JSON.parse(readFileSync(filename, "utf8"));
    const result = CheckpointSchema.safeParse(content);
    expect(result.success).toBe(true);
  });

  it("checkpoint has required fields", () => {
    const filename = createPauseCheckpoint(tmpDir);
    const content = JSON.parse(readFileSync(filename, "utf8"));
    expect(content.session_id).toBeDefined();
    expect(content.timestamp).toBeDefined();
    expect(content.version).toBe("2.3.0");
  });

  it("checkpoint file path contains session_id", () => {
    const filename = createPauseCheckpoint(tmpDir);
    expect(filename).toContain(".omg/state/checkpoint-");
  });
});
