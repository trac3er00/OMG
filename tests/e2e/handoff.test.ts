import { describe, test, expect } from "bun:test";
import {
  SubagentDispatcher,
  MAX_JOBS,
  type DispatchResult,
} from "../../src/orchestration/dispatcher.js";

describe("e2e/handoff", () => {
  describe("dispatcher module loads and exports", () => {
    test("SubagentDispatcher is constructable", () => {
      const dispatcher = SubagentDispatcher.create();
      expect(dispatcher).toBeDefined();
    });

    test("MAX_JOBS constant is exported and positive", () => {
      expect(MAX_JOBS).toBeGreaterThan(0);
      expect(MAX_JOBS).toBe(100);
    });

    test("static create accepts empty options", () => {
      const dispatcher = SubagentDispatcher.create({});
      expect(dispatcher).toBeDefined();
    });
  });

  describe("task routing via dispatcher", () => {
    test("dispatcher routes a task and returns a completed result", async () => {
      let jobCounter = 0;
      const dispatcher = SubagentDispatcher.create({
        concurrency: 1,
        idGenerator: () => `test-job-${++jobCounter}`,
      });

      const handle = await dispatcher.dispatch({
        agentName: "test-agent",
        prompt: "Fix a simple bug",
      });

      expect(handle.id).toBe("test-job-1");

      const result: DispatchResult = await handle.completion;
      expect(result.status).toBe("completed");
      expect(result.exitCode).toBe(0);
    });

    test("dispatcher preserves task context through artifacts", async () => {
      const dispatcher = SubagentDispatcher.create({
        concurrency: 1,
        idGenerator: () => "ctx-job-1",
      });

      const handle = await dispatcher.dispatch({
        agentName: "context-agent",
        prompt: "Analyze codebase structure",
      });

      const artifacts: Array<{
        type: string;
        payload: Record<string, unknown>;
      }> = [];
      const result = await handle.completion;

      for await (const artifact of handle.artifacts) {
        artifacts.push(artifact);
      }

      expect(result.status).toBe("completed");
      expect(artifacts.length).toBeGreaterThanOrEqual(1);
      expect(artifacts[0]?.payload).toHaveProperty("agent", "context-agent");
      expect(artifacts[0]?.payload).toHaveProperty(
        "prompt",
        "Analyze codebase structure",
      );
    });

    test("custom runner receives correct task and context", async () => {
      const receivedTasks: Array<{ agentName: string; prompt: string }> = [];

      const dispatcher = SubagentDispatcher.create({
        concurrency: 1,
        idGenerator: () => "custom-job-1",
        runner: async (task, context) => {
          receivedTasks.push({
            agentName: task.agentName,
            prompt: task.prompt,
          });
          context.emitArtifact({
            type: "custom-result",
            producedAt: new Date().toISOString(),
            payload: { handled: true },
          });
          return { exitCode: 0 };
        },
      });

      const handle = await dispatcher.dispatch({
        agentName: "routing-agent",
        prompt: "Route this task appropriately",
      });

      await handle.completion;

      expect(receivedTasks).toHaveLength(1);
      expect(receivedTasks[0]?.agentName).toBe("routing-agent");
      expect(receivedTasks[0]?.prompt).toBe("Route this task appropriately");
    });
  });

  describe("session lifecycle context preservation", () => {
    test("multiple sequential dispatches maintain isolation", async () => {
      let counter = 0;
      const dispatcher = SubagentDispatcher.create({
        concurrency: 1,
        idGenerator: () => `seq-job-${++counter}`,
      });

      const handle1 = await dispatcher.dispatch({
        agentName: "agent-a",
        prompt: "Task A",
      });
      const result1 = await handle1.completion;

      const handle2 = await dispatcher.dispatch({
        agentName: "agent-b",
        prompt: "Task B",
      });
      const result2 = await handle2.completion;

      expect(result1.jobId).toBe("seq-job-1");
      expect(result2.jobId).toBe("seq-job-2");
      expect(result1.status).toBe("completed");
      expect(result2.status).toBe("completed");
    });

    test("failed runner returns failed status with error", async () => {
      const dispatcher = SubagentDispatcher.create({
        concurrency: 1,
        idGenerator: () => "fail-job-1",
        runner: async () => {
          throw new Error("Simulated runner failure");
        },
      });

      const handle = await dispatcher.dispatch({
        agentName: "failing-agent",
        prompt: "This will fail",
      });

      const result = await handle.completion;
      expect(result.status).toBe("failed");
      expect(result.exitCode).toBe(1);
      expect(result.error).toContain("Simulated runner failure");
    });
  });
});
