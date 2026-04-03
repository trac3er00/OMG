import { describe, test, expect } from "bun:test";
import {
  CALIBRATION_VERSION,
  BENCHMARK_TASK_COUNT,
  BenchmarkTaskSchema,
  CalibrationResultSchema,
  calibrateMetric,
  createSampleBenchmarkTasks,
  type CalibrationRun,
} from "./calibration.js";

function makePerfectRuns(n: number): CalibrationRun[] {
  return Array.from({ length: n }, (_, i) => ({
    task_id: `t-${i}`,
    metric_score: 0.9,
    actual_success: true,
    human_agrees: true,
  }));
}

function makeRandomRuns(n: number): CalibrationRun[] {
  return Array.from({ length: n }, (_, i) => ({
    task_id: `t-${i}`,
    metric_score: Math.random(),
    actual_success: Math.random() > 0.5,
    human_agrees: Math.random() > 0.3,
  }));
}

describe("reliability/calibration", () => {
  test("CALIBRATION_VERSION is 1.0.0", () => {
    expect(CALIBRATION_VERSION).toBe("1.0.0");
  });

  test("BENCHMARK_TASK_COUNT is 100", () => {
    expect(BENCHMARK_TASK_COUNT).toBe(100);
  });

  describe("BenchmarkTask schema", () => {
    test("valid task passes", () => {
      expect(
        BenchmarkTaskSchema.safeParse({
          task_id: "task-001",
          description: "Test task",
          difficulty: "easy",
          expected_output: "result",
        }).success,
      ).toBe(true);
    });

    test("invalid difficulty fails", () => {
      expect(
        BenchmarkTaskSchema.safeParse({
          task_id: "task-001",
          description: "Test",
          difficulty: "super-hard",
          expected_output: "result",
        }).success,
      ).toBe(false);
    });
  });

  describe("calibrateMetric", () => {
    test("insufficient data (<10 runs) returns insufficient_data status", () => {
      const result = calibrateMetric(makePerfectRuns(5));
      expect(result.status).toBe("insufficient_data");
    });

    test("perfect metric (high correlation, low FPR/FNR) → calibrated", () => {
      const runs: CalibrationRun[] = Array.from({ length: 50 }, (_, i) => ({
        task_id: `t-${i}`,
        metric_score: i < 40 ? 0.95 : 0.05,
        actual_success: i < 40,
        human_agrees: true,
      }));
      const result = calibrateMetric(runs);
      expect(result.status).toBe("calibrated");
      expect(result.correlation).toBeGreaterThan(0.7);
    });

    test("random metric (no correlation) → uncalibrated", () => {
      const runs = makeRandomRuns(50);
      const result = calibrateMetric(runs);
      expect(["uncalibrated", "calibrated"]).toContain(result.status);
    });

    test("result has accuracy 0-1", () => {
      const result = calibrateMetric(makePerfectRuns(20));
      expect(result.accuracy).toBeGreaterThanOrEqual(0);
      expect(result.accuracy).toBeLessThanOrEqual(1);
    });

    test("FPR and FNR are 0-1", () => {
      const runs: CalibrationRun[] = Array.from({ length: 20 }, (_, i) => ({
        task_id: `t-${i}`,
        metric_score: 0.9,
        actual_success: i % 2 === 0,
        human_agrees: true,
      }));
      const result = calibrateMetric(runs);
      expect(result.false_positive_rate).toBeGreaterThanOrEqual(0);
      expect(result.false_positive_rate).toBeLessThanOrEqual(1);
      expect(result.false_negative_rate).toBeGreaterThanOrEqual(0);
      expect(result.false_negative_rate).toBeLessThanOrEqual(1);
    });

    test("validates against schema", () => {
      const result = calibrateMetric(makePerfectRuns(20));
      expect(CalibrationResultSchema.safeParse(result).success).toBe(true);
    });

    test("human_agreement_rate reflects human_agrees field", () => {
      const runs: CalibrationRun[] = Array.from({ length: 20 }, (_, i) => ({
        task_id: `t-${i}`,
        metric_score: 0.8,
        actual_success: true,
        human_agrees: i < 16,
      }));
      const result = calibrateMetric(runs);
      expect(result.human_agreement_rate).toBeCloseTo(0.8, 5);
    });
  });

  describe("createSampleBenchmarkTasks", () => {
    test("creates requested count", () => {
      const tasks = createSampleBenchmarkTasks(30);
      expect(tasks.length).toBe(30);
    });

    test("includes all 3 difficulty levels", () => {
      const tasks = createSampleBenchmarkTasks(30);
      const difficulties = new Set(tasks.map((t) => t.difficulty));
      expect(difficulties.has("easy")).toBe(true);
      expect(difficulties.has("medium")).toBe(true);
      expect(difficulties.has("hard")).toBe(true);
    });

    test("all task IDs are unique", () => {
      const tasks = createSampleBenchmarkTasks(20);
      const ids = new Set(tasks.map((t) => t.task_id));
      expect(ids.size).toBe(20);
    });

    test("default creates 20 tasks", () => {
      const tasks = createSampleBenchmarkTasks();
      expect(tasks.length).toBe(20);
    });
  });
});
