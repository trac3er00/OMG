import { describe, expect, test } from "bun:test";
import type { WorkerTask } from "../interfaces/orchestration.js";
import { ExecKernel } from "./exec-kernel.js";

const TASK: WorkerTask = {
  agentName: "codex",
  prompt: "implement orchestration tests",
  order: 2,
  timeout: 30,
};

describe("ExecKernel", () => {
  test("default executor passes task through and stores run state", async () => {
    const kernel = ExecKernel.create({
      createRunId: () => "run-123",
      now: () => new Date("2026-04-10T12:00:00.000Z"),
    });

    const result = await kernel.run(TASK);

    expect(result.runId).toBe("run-123");
    expect(result.executionResult).toEqual({
      status: "ok",
      agentName: TASK.agentName,
      prompt: TASK.prompt,
      order: TASK.order,
      timeout: TASK.timeout,
    });
    expect(kernel.getRunState("run-123")).toEqual(result);
  });

  test("custom executor receives context and persists namespaced state", async () => {
    const kernel = new ExecKernel({
      createRunId: () => "run-ctx",
      now: () => new Date("2026-04-10T12:34:56.000Z"),
      executor: {
        async execute(task, context) {
          expect(context.runId).toBe("run-ctx");
          expect(context.getState("missing")).toBeUndefined();
          context.setState("taskId", task.agentName);
          context.setState("attempt", 1);

          return {
            ok: true,
            snapshot: context.snapshot(),
          };
        },
      },
    });

    const result = await kernel.run(TASK);

    expect(result.stateNamespace).toEqual({
      taskId: "codex",
      attempt: 1,
    });
    expect(result.executionResult).toEqual({
      ok: true,
      snapshot: {
        taskId: "codex",
        attempt: 1,
      },
    });
  });
});
