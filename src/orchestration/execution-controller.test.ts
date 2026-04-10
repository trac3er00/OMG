import { describe, expect, test } from "bun:test";
import {
  DEFAULT_CONCURRENCY,
  ExecutionController,
  type ExecutableTask,
} from "./execution-controller.js";

const TASK: ExecutableTask = {
  id: "task-1",
  prompt: "fix typo in README",
  deps: [],
  skills: [],
  priority: "medium",
  timeout_ms: 5_000,
};

describe("ExecutionController", () => {
  test("uses documented mode concurrency defaults", () => {
    expect(DEFAULT_CONCURRENCY).toEqual({
      ultrawork: 8,
      team: 4,
      sequential: 1,
    });
  });

  test("registerTask returns routing metadata and execute yields task results", async () => {
    const controller = new ExecutionController("sequential");
    const seenCategories: string[] = [];

    const registration = controller.registerTask(
      TASK,
      async (_task, category) => {
        seenCategories.push(category);
        return { ok: true, category };
      },
    );

    const results = [];
    for await (const result of controller.execute()) {
      results.push(result);
    }

    expect(registration.taskId).toBe("task-1");
    expect(registration.provider).toBeDefined();
    expect(registration.reasoning.length).toBeGreaterThan(0);
    expect(seenCategories).toHaveLength(1);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      id: "task-1",
      status: "fulfilled",
      value: { ok: true, category: seenCategories[0] },
    });
  });
});
