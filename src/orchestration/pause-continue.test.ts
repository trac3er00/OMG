import { describe, expect, test } from "bun:test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { CheckpointSystem } from "../context/checkpoint.js";
import {
  createCompactState,
  deserializeState,
  serializeState,
} from "../context/workspace-reconstruction.js";
import { OrchestrationSession } from "./session.js";

function createProjectDir(name: string): string {
  const projectDir = `/tmp/${name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  mkdirSync(join(projectDir, ".omg", "state"), { recursive: true });
  return projectDir;
}

describe("orchestration pause/continue checkpoint round-trip", () => {
  test("session snapshot state survives checkpoint save and restore", () => {
    const projectDir = createProjectDir("omg-orch-pause-continue");

    try {
      const session = OrchestrationSession.create({
        idGenerator: () => "orch-session-1",
        now: () => new Date("2026-04-10T12:00:00.000Z"),
        mode: "team",
        projectDir,
      });

      session.recordFileReference("src/orchestration/exec-kernel.ts");
      const snapshot = session.snapshot();

      serializeState(
        createCompactState(`resume:${snapshot.sessionId}`, {
          evidence_index: [snapshot.mode, snapshot.status],
          open_hypotheses: snapshot.agents.map((agent) => agent.taskId),
          next_actions: [
            `tasks:${snapshot.tasksCompleted}/${snapshot.tasksTotal}`,
            `freshness:${snapshot.durabilityMetrics.averageFreshnessScore}`,
          ],
          decayEventCount: snapshot.durabilityMetrics.decayEventCount,
        }),
        projectDir,
      );

      const checkpoint = new CheckpointSystem(projectDir, 1).onToolCall();
      expect(checkpoint).not.toBeNull();

      serializeState(createCompactState("mutated-state"), projectDir);
      const restored = new CheckpointSystem(projectDir).restoreLatest();
      const restoredState = deserializeState(projectDir);

      expect(restored?.checkpoint_id).toBeDefined();
      expect(restored?.state.goal).toBe(`resume:${snapshot.sessionId}`);
      expect(restoredState?.goal).toBe(`resume:${snapshot.sessionId}`);
      expect(restoredState?.evidence_index).toEqual([
        snapshot.mode,
        snapshot.status,
      ]);
      expect(restoredState?.next_actions).toEqual([
        `tasks:${snapshot.tasksCompleted}/${snapshot.tasksTotal}`,
        `freshness:${snapshot.durabilityMetrics.averageFreshnessScore}`,
      ]);
      expect(restoredState?.decayEventCount).toBe(
        snapshot.durabilityMetrics.decayEventCount,
      );
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});
