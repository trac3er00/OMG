import { z } from "zod";

export const CALIBRATION_VERSION = "1.0.0";
export const BENCHMARK_TASK_COUNT = 100;

export type BenchmarkDifficulty = "easy" | "medium" | "hard";

export const BenchmarkTaskSchema = z.object({
  task_id: z.string(),
  description: z.string(),
  difficulty: z.enum(["easy", "medium", "hard"]),
  expected_output: z.string(),
  tolerance: z.number().min(0).max(1).default(0),
});
export type BenchmarkTask = z.infer<typeof BenchmarkTaskSchema>;

export const CalibrationResultSchema = z.object({
  schema_version: z.literal(CALIBRATION_VERSION),
  calibration_id: z.string(),
  task_count: z.number().int(),
  correct_count: z.number().int(),
  accuracy: z.number().min(0).max(1),
  correlation: z.number().min(-1).max(1),
  false_positive_rate: z.number().min(0).max(1),
  false_negative_rate: z.number().min(0).max(1),
  human_agreement_rate: z.number().min(0).max(1),
  status: z.enum(["calibrated", "uncalibrated", "insufficient_data"]),
  calibrated_at: z.string(),
});
export type CalibrationResult = z.infer<typeof CalibrationResultSchema>;

const CALIBRATION_THRESHOLDS = {
  min_correlation: 0.7,
  max_fpr: 0.1,
  max_fnr: 0.2,
  min_human_agreement: 0.8,
};

function computeCorrelation(xs: number[], ys: number[]): number {
  if (xs.length !== ys.length || xs.length < 2) return 0;
  const n = xs.length;
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = ys.reduce((a, b) => a + b, 0) / n;
  const num = xs.reduce(
    (sum, x, i) => sum + (x - meanX) * ((ys[i] ?? 0) - meanY),
    0,
  );
  const denX = Math.sqrt(xs.reduce((sum, x) => sum + (x - meanX) ** 2, 0));
  const denY = Math.sqrt(ys.reduce((sum, y) => sum + (y - meanY) ** 2, 0));
  if (denX === 0 || denY === 0) return 0;
  return num / (denX * denY);
}

export interface CalibrationRun {
  readonly task_id: string;
  readonly metric_score: number;
  readonly actual_success: boolean;
  readonly human_agrees: boolean;
}

export function calibrateMetric(
  runs: readonly CalibrationRun[],
): CalibrationResult {
  if (runs.length < 10) {
    return CalibrationResultSchema.parse({
      schema_version: CALIBRATION_VERSION,
      calibration_id: `cal-${Date.now()}`,
      task_count: runs.length,
      correct_count: 0,
      accuracy: 0,
      correlation: 0,
      false_positive_rate: 0,
      false_negative_rate: 0,
      human_agreement_rate: 0,
      status: "insufficient_data",
      calibrated_at: new Date().toISOString(),
    });
  }

  const metricScores = runs.map((r) => r.metric_score);
  const actualOutcomes = runs.map((r) => (r.actual_success ? 1.0 : 0.0));

  const correlation = computeCorrelation(metricScores, actualOutcomes);

  const THRESHOLD = 0.5;
  const tp = runs.filter(
    (r) => r.metric_score >= THRESHOLD && r.actual_success,
  ).length;
  const fp = runs.filter(
    (r) => r.metric_score >= THRESHOLD && !r.actual_success,
  ).length;
  const tn = runs.filter(
    (r) => r.metric_score < THRESHOLD && !r.actual_success,
  ).length;
  const fn = runs.filter(
    (r) => r.metric_score < THRESHOLD && r.actual_success,
  ).length;

  const fpr = fp + tn === 0 ? 0 : fp / (fp + tn);
  const fnr = tp + fn === 0 ? 0 : fn / (tp + fn);
  const accuracy = (tp + tn) / runs.length;
  const human_agreement_rate =
    runs.filter((r) => r.human_agrees).length / runs.length;

  const isCalibrated =
    Math.abs(correlation) >= CALIBRATION_THRESHOLDS.min_correlation &&
    fpr <= CALIBRATION_THRESHOLDS.max_fpr &&
    fnr <= CALIBRATION_THRESHOLDS.max_fnr &&
    human_agreement_rate >= CALIBRATION_THRESHOLDS.min_human_agreement;

  return CalibrationResultSchema.parse({
    schema_version: CALIBRATION_VERSION,
    calibration_id: `cal-${Date.now()}`,
    task_count: runs.length,
    correct_count: tp + tn,
    accuracy,
    correlation,
    false_positive_rate: fpr,
    false_negative_rate: fnr,
    human_agreement_rate,
    status: isCalibrated ? "calibrated" : "uncalibrated",
    calibrated_at: new Date().toISOString(),
  });
}

export function createSampleBenchmarkTasks(count = 20): BenchmarkTask[] {
  const difficulties: BenchmarkDifficulty[] = ["easy", "medium", "hard"];
  return Array.from({ length: count }, (_, i) => {
    const difficulty = difficulties[i % 3] ?? "medium";
    return BenchmarkTaskSchema.parse({
      task_id: `task-${String(i + 1).padStart(3, "0")}`,
      description: `Benchmark task ${i + 1}: ${difficulty} complexity verification`,
      difficulty,
      expected_output: `expected-output-${i + 1}`,
      tolerance: 0,
    });
  });
}
