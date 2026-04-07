import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";
import { readJsonFile } from "../state/atomic-io.js";
import {
  CheckpointSystem,
  DEFAULT_CHECKPOINT_INTERVAL,
  MAX_ACTIVE_CHECKPOINTS,
} from "./checkpoint.js";
import {
  createCompactState,
  serializeState,
} from "./workspace-reconstruction.js";

const TEST_DIR = "/tmp/omg-checkpoint-test";

function setup(dir = TEST_DIR) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(join(dir, ".omg", "state"), { recursive: true });
  const state = createCompactState("Test goal", { evidence_index: ["a.json"] });
  serializeState(state, dir);
}

beforeEach(() => setup());
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("checkpoint", () => {
  test("DEFAULT_CHECKPOINT_INTERVAL is 50", () => {
    expect(DEFAULT_CHECKPOINT_INTERVAL).toBe(50);
  });

  test("MAX_ACTIVE_CHECKPOINTS is 5", () => {
    expect(MAX_ACTIVE_CHECKPOINTS).toBe(5);
  });

  describe("onToolCall", () => {
    test("returns null before interval reached", () => {
      const sys = new CheckpointSystem(TEST_DIR, 50);
      for (let i = 0; i < 49; i++) {
        const result = sys.onToolCall();
        expect(result).toBeNull();
      }
    });

    test("creates checkpoint at interval boundary", () => {
      const sys = new CheckpointSystem(TEST_DIR, 50);
      let checkpoint = null;
      for (let i = 0; i < 50; i++) {
        checkpoint = sys.onToolCall();
      }
      expect(checkpoint).not.toBeNull();
      expect(checkpoint?.checkpoint_id).toBeDefined();
      expect(checkpoint?.tool_call_count).toBe(50);
    });

    test("creates checkpoint at second interval (100)", () => {
      const sys = new CheckpointSystem(TEST_DIR, 50);
      const checkpoints = [];
      for (let i = 0; i < 100; i++) {
        const result = sys.onToolCall();
        if (result) checkpoints.push(result);
      }
      expect(checkpoints.length).toBe(2);
      expect(checkpoints[1]?.tool_call_count).toBe(100);
    });

    test("smaller interval works correctly", () => {
      const sys = new CheckpointSystem(TEST_DIR, 5);
      let checkpointCount = 0;
      for (let i = 0; i < 15; i++) {
        const result = sys.onToolCall();
        if (result) checkpointCount++;
      }
      expect(checkpointCount).toBe(3);
    });
  });

  describe("saveCheckpoint", () => {
    test("creates checkpoint file", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      const result = sys.saveCheckpoint();
      expect(existsSync(result.path)).toBe(true);
    });

    test("checkpoint has unique ID", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      const r1 = sys.saveCheckpoint();
      const r2 = sys.saveCheckpoint();
      expect(r1.checkpoint_id).not.toBe(r2.checkpoint_id);
    });

    test("checkpoint persists optional durability metadata", () => {
      serializeState(
        createCompactState("Durable goal", {
          contextFreshnessScore: 72,
          lastReconstructionAt: "2026-04-07T12:00:00.000Z",
          decayEventCount: 3,
        }),
        TEST_DIR,
      );

      const sys = new CheckpointSystem(TEST_DIR);
      const result = sys.saveCheckpoint();
      const saved = readJsonFile<{ meta: Record<string, unknown> }>(
        result.path,
      );

      expect(saved?.meta.contextFreshnessScore).toBe(72);
      expect(saved?.meta.lastReconstructionAt).toBe("2026-04-07T12:00:00.000Z");
      expect(saved?.meta.decayEventCount).toBe(3);
    });
  });

  describe("restoreLatest", () => {
    test("returns null when no checkpoints exist", () => {
      const sys = new CheckpointSystem("/tmp/empty-dir-test-xyz");
      const result = sys.restoreLatest();
      expect(result).toBeNull();
    });

    test("restores state from checkpoint", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      sys.saveCheckpoint();
      const result = sys.restoreLatest();
      expect(result).not.toBeNull();
      expect(result?.state.goal).toBe("Test goal");
      expect(result?.checkpoint_id).toBeDefined();
    });

    test("restoration completes quickly (< 5000ms)", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      sys.saveCheckpoint();
      const result = sys.restoreLatest();
      expect(result?.elapsed_ms).toBeLessThan(5000);
    });
  });

  describe("GC", () => {
    test("archives checkpoints beyond MAX_ACTIVE_CHECKPOINTS", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      for (let i = 0; i < MAX_ACTIVE_CHECKPOINTS + 2; i++) {
        sys.saveCheckpoint();
      }
      const archiveDir = join(
        TEST_DIR,
        ".omg",
        "state",
        "checkpoints",
        "archive",
      );
      expect(existsSync(archiveDir)).toBe(true);
    });
  });

  describe("getToolCallCount", () => {
    test("tracks tool calls correctly", () => {
      const sys = new CheckpointSystem(TEST_DIR);
      expect(sys.getToolCallCount()).toBe(0);
      sys.onToolCall();
      sys.onToolCall();
      sys.onToolCall();
      expect(sys.getToolCallCount()).toBe(3);
    });
  });
});
