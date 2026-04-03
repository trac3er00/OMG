import { describe, expect, test } from "bun:test";
import { getModeConfig, planTasks, estimateDuration } from "./modes.js";
import { OrchestrationTaskSchema, type OrchestrationTask } from "./session.js";

function task(
  id: string,
  deps: string[] = [],
  priority: "high" | "medium" | "low" = "medium",
): OrchestrationTask {
  return OrchestrationTaskSchema.parse({
    id,
    prompt: `do ${id}`,
    deps,
    priority,
    timeout_ms: 10_000,
  });
}

describe("getModeConfig", () => {
  test("ultrawork defaults to concurrency 8 with reordering", () => {
    const config = getModeConfig("ultrawork");
    expect(config.concurrency).toBe(8);
    expect(config.taskReordering).toBe(true);
    expect(config.failFast).toBe(false);
  });

  test("team defaults to concurrency 4 without reordering", () => {
    const config = getModeConfig("team");
    expect(config.concurrency).toBe(4);
    expect(config.taskReordering).toBe(false);
  });

  test("sequential defaults to concurrency 1 with failFast", () => {
    const config = getModeConfig("sequential");
    expect(config.concurrency).toBe(1);
    expect(config.failFast).toBe(true);
    expect(config.taskReordering).toBe(false);
  });

  test("overrides are applied correctly", () => {
    const config = getModeConfig("ultrawork", {
      concurrency: 16,
      failFast: true,
    });
    expect(config.concurrency).toBe(16);
    expect(config.failFast).toBe(true);
    expect(config.mode).toBe("ultrawork");
  });
});

describe("planTasks", () => {
  test("empty task list produces empty plan", () => {
    const config = getModeConfig("ultrawork");
    const plan = planTasks([], config);
    expect(plan.tasks).toHaveLength(0);
    expect(plan.waves).toHaveLength(0);
    expect(plan.leaderTaskId).toBeNull();
  });

  test("independent tasks form a single wave in ultrawork", () => {
    const tasks = [task("a"), task("b"), task("c")];
    const config = getModeConfig("ultrawork");
    const plan = planTasks(tasks, config);
    expect(plan.waves).toHaveLength(1);
    expect(plan.waves[0]).toHaveLength(3);
  });

  test("dependent tasks form multiple waves", () => {
    const tasks = [task("a"), task("b", ["a"]), task("c", ["b"])];
    const config = getModeConfig("ultrawork");
    const plan = planTasks(tasks, config);
    expect(plan.waves).toHaveLength(3);
    expect(plan.waves[0]).toEqual(["a"]);
    expect(plan.waves[1]).toEqual(["b"]);
    expect(plan.waves[2]).toEqual(["c"]);
  });

  test("sequential mode processes one task per wave", () => {
    const tasks = [task("a"), task("b"), task("c")];
    const config = getModeConfig("sequential");
    const plan = planTasks(tasks, config);
    expect(plan.waves).toHaveLength(3);
    for (const wave of plan.waves) {
      expect(wave).toHaveLength(1);
    }
  });

  test("ultrawork reorders by priority (high first)", () => {
    const tasks = [
      task("low-pri", [], "low"),
      task("high-pri", [], "high"),
      task("med-pri", [], "medium"),
    ];
    const config = getModeConfig("ultrawork");
    const plan = planTasks(tasks, config);
    expect(plan.waves[0][0]).toBe("high-pri");
    expect(plan.waves[0][2]).toBe("low-pri");
  });

  test("cycle detection throws error", () => {
    const tasks = [task("a", ["b"]), task("b", ["a"])];
    const config = getModeConfig("ultrawork");
    expect(() => planTasks(tasks, config)).toThrow("Cycle detected");
  });

  test("team mode sets leaderTaskId when configured", () => {
    const tasks = [task("leader"), task("worker-1"), task("worker-2")];
    const config = getModeConfig("team", { leaderTaskId: "leader" });
    const plan = planTasks(tasks, config);
    expect(plan.leaderTaskId).toBe("leader");
  });

  test("team mode with invalid leaderTaskId returns null", () => {
    const tasks = [task("a"), task("b")];
    const config = getModeConfig("team", { leaderTaskId: "nonexistent" });
    const plan = planTasks(tasks, config);
    expect(plan.leaderTaskId).toBeNull();
  });

  test("concurrency limits wave size", () => {
    const tasks = Array.from({ length: 10 }, (_, i) => task(`t${i}`));
    const config = getModeConfig("ultrawork", { concurrency: 3 });
    const plan = planTasks(tasks, config);
    for (const wave of plan.waves) {
      expect(wave.length).toBeLessThanOrEqual(3);
    }
  });
});

describe("estimateDuration", () => {
  test("sequential sums all task timeouts", () => {
    const tasks = [task("a"), task("b"), task("c")];
    const config = getModeConfig("sequential");
    const plan = planTasks(tasks, config);
    const duration = estimateDuration(plan, config);
    expect(duration).toBe(30_000);
  });

  test("parallel takes max per wave", () => {
    const tasks = [task("a"), task("b"), task("c")];
    const config = getModeConfig("ultrawork");
    const plan = planTasks(tasks, config);
    const duration = estimateDuration(plan, config);
    expect(duration).toBe(10_000);
  });
});
