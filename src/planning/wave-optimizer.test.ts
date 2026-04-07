import { describe, test, expect } from "bun:test";
import { optimizeWaves, validateWavePlan, type Task } from "./wave-optimizer";

function task(id: string, dependsOn: string[] = []): Task {
  return { id, description: `Task ${id}`, dependsOn };
}

describe("optimizeWaves", () => {
  test("parallel: 10-task plan with 3 independent groups produces 3 waves", () => {
    // given: 3 root tasks, each with 2 children, plus 1 grandchild from group A
    const tasks: Task[] = [
      task("a1"),
      task("a2"),
      task("a3"),
      task("b1", ["a1"]),
      task("b2", ["a1"]),
      task("b3", ["a2"]),
      task("b4", ["a2"]),
      task("b5", ["a3"]),
      task("b6", ["a3"]),
      task("c1", ["b1", "b2"]),
    ];

    const result = optimizeWaves(tasks);

    expect(result.waves).toHaveLength(3);
    expect(result.totalTasks).toBe(10);
    expect(result.maxParallelism).toBeGreaterThanOrEqual(3);

    const wave1Ids = result.waves[0].tasks.map((t) => t.id);
    expect(wave1Ids).toEqual(["a1", "a2", "a3"]);
    expect(result.waves[0].canRunInParallel).toBe(true);

    const wave2Ids = result.waves[1].tasks.map((t) => t.id);
    expect(wave2Ids).toEqual(["b1", "b2", "b3", "b4", "b5", "b6"]);

    const wave3Ids = result.waves[2].tasks.map((t) => t.id);
    expect(wave3Ids).toEqual(["c1"]);
  });

  test("dependency-order: task B after task A if B depends on A", () => {
    const tasks = [task("B", ["A"]), task("A")];

    const result = optimizeWaves(tasks);

    const aWave = result.waves.find((w) => w.tasks.some((t) => t.id === "A"))!;
    const bWave = result.waves.find((w) => w.tasks.some((t) => t.id === "B"))!;
    expect(aWave.waveNumber).toBeLessThan(bWave.waveNumber);
  });

  test("single-task: single task produces single wave", () => {
    const result = optimizeWaves([task("only")]);

    expect(result.waves).toHaveLength(1);
    expect(result.totalTasks).toBe(1);
    expect(result.maxParallelism).toBe(1);
    expect(result.criticalPathLength).toBe(1);
    expect(result.waves[0].canRunInParallel).toBe(false);
  });

  test("chain: linear chain A→B→C produces 3 sequential waves", () => {
    const tasks = [task("A"), task("B", ["A"]), task("C", ["B"])];

    const result = optimizeWaves(tasks);

    expect(result.waves).toHaveLength(3);
    expect(result.criticalPathLength).toBe(3);
    expect(result.maxParallelism).toBe(1);
    expect(result.waves[0].tasks[0].id).toBe("A");
    expect(result.waves[1].tasks[0].id).toBe("B");
    expect(result.waves[2].tasks[0].id).toBe("C");
  });

  test("diamond: A→B,A→C,B→D,C→D produces 3 waves", () => {
    const tasks = [
      task("A"),
      task("B", ["A"]),
      task("C", ["A"]),
      task("D", ["B", "C"]),
    ];

    const result = optimizeWaves(tasks);

    expect(result.waves).toHaveLength(3);
    expect(result.waves[0].tasks.map((t) => t.id)).toEqual(["A"]);
    expect(result.waves[1].tasks.map((t) => t.id)).toEqual(["B", "C"]);
    expect(result.waves[1].canRunInParallel).toBe(true);
    expect(result.waves[2].tasks.map((t) => t.id)).toEqual(["D"]);
  });

  test("empty input returns empty result", () => {
    const result = optimizeWaves([]);

    expect(result.waves).toHaveLength(0);
    expect(result.totalTasks).toBe(0);
    expect(result.maxParallelism).toBe(0);
    expect(result.criticalPathLength).toBe(0);
  });

  test("throws on dependency cycle", () => {
    const tasks = [task("A", ["B"]), task("B", ["A"])];

    expect(() => optimizeWaves(tasks)).toThrow(/cycle/i);
  });

  test("throws on unknown dependency", () => {
    const tasks = [task("A", ["missing"])];

    expect(() => optimizeWaves(tasks)).toThrow(/unknown/i);
  });
});

describe("validateWavePlan", () => {
  test("no-violations: returns empty array for valid plan", () => {
    const tasks = [
      task("A"),
      task("B", ["A"]),
      task("C", ["A"]),
      task("D", ["B", "C"]),
    ];

    const result = optimizeWaves(tasks);
    const violations = validateWavePlan(result);

    expect(violations).toEqual([]);
  });

  test("detects dependency in same wave as violation", () => {
    const badResult = {
      waves: [
        {
          waveNumber: 1,
          tasks: [task("A"), task("B", ["A"])],
          canRunInParallel: true,
        },
      ],
      totalTasks: 2,
      maxParallelism: 2,
      criticalPathLength: 1,
    };

    const violations = validateWavePlan(badResult);

    expect(violations.length).toBeGreaterThan(0);
    expect(violations[0]).toContain("not in an earlier wave");
  });

  test("detects task count mismatch", () => {
    const badResult = {
      waves: [
        {
          waveNumber: 1,
          tasks: [task("A")],
          canRunInParallel: false,
        },
      ],
      totalTasks: 5,
      maxParallelism: 1,
      criticalPathLength: 1,
    };

    const violations = validateWavePlan(badResult);

    expect(violations.some((v) => v.includes("totalTasks"))).toBe(true);
  });
});
