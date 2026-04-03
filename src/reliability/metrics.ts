import { z } from "zod";
import { appendFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";

export const RELIABILITY_VERSION = "1.0.0";

export type MetricDimension =
  | "consistency"
  | "robustness"
  | "predictability"
  | "safety";

export const MetricResultSchema = z.object({
  metric_id: z.string(),
  dimension: z.enum(["consistency", "robustness", "predictability", "safety"]),
  name: z.string(),
  score: z.number().min(0).max(1),
  threshold: z.number().min(0).max(1),
  status: z.enum(["pass", "fail", "unknown"]),
  sample_count: z.number().int().min(0),
  details: z.record(z.string(), z.unknown()).optional(),
});
export type MetricResult = z.infer<typeof MetricResultSchema>;

export const ReliabilitySnapshotSchema = z.object({
  schema_version: z.literal(RELIABILITY_VERSION),
  snapshot_id: z.string(),
  agent_id: z.string(),
  task_type: z.string(),
  metrics: z.array(MetricResultSchema),
  overall_score: z.number().min(0).max(1),
  overall_status: z.enum(["pass", "fail", "partial"]),
  recorded_at: z.string(),
});
export type ReliabilitySnapshot = z.infer<typeof ReliabilitySnapshotSchema>;

const DEFAULT_THRESHOLDS: Record<string, number> = {
  "same-input-consistency": 0.8,
  "cross-run-consistency": 0.75,
  "intra-run-stability": 0.8,
  "failure-predictability": 0.7,
  "error-pattern-consistency": 0.7,
  "error-severity-bounding": 0.8,
  "safe-failure-modes": 0.85,
};

export function measureSameInputConsistency(
  outputs: readonly string[],
): MetricResult {
  if (outputs.length === 0) {
    return buildMetric(
      "same-input-consistency",
      "consistency",
      "Same-Input Consistency",
      0,
      0,
      "unknown",
    );
  }
  const unique = new Set(outputs).size;
  const score = 1 - (unique - 1) / Math.max(outputs.length - 1, 1);
  return buildMetric(
    "same-input-consistency",
    "consistency",
    "Same-Input Consistency",
    score,
    outputs.length,
  );
}

export function measureCrossRunConsistency(
  runScores: readonly number[],
): MetricResult {
  if (runScores.length === 0) {
    return buildMetric(
      "cross-run-consistency",
      "consistency",
      "Cross-Run Consistency",
      0,
      0,
      "unknown",
    );
  }
  const mean = runScores.reduce((a, b) => a + b, 0) / runScores.length;
  const variance =
    runScores.reduce((sum, s) => sum + (s - mean) ** 2, 0) / runScores.length;
  const score = Math.max(0, 1 - Math.sqrt(variance));
  return buildMetric(
    "cross-run-consistency",
    "consistency",
    "Cross-Run Consistency",
    score,
    runScores.length,
  );
}

export function measureIntraRunStability(
  sequentialOutputs: readonly string[],
): MetricResult {
  if (sequentialOutputs.length < 2) {
    return buildMetric(
      "intra-run-stability",
      "consistency",
      "Intra-Run Stability",
      1,
      sequentialOutputs.length,
    );
  }
  let transitions = 0;
  for (let i = 1; i < sequentialOutputs.length; i++) {
    if (sequentialOutputs[i] !== sequentialOutputs[i - 1]) transitions++;
  }
  const score = 1 - transitions / (sequentialOutputs.length - 1);
  return buildMetric(
    "intra-run-stability",
    "consistency",
    "Intra-Run Stability",
    score,
    sequentialOutputs.length,
  );
}

export function measureErrorSeverityBounding(
  errorSeverities: readonly number[],
  maxAllowed = 0.8,
): MetricResult {
  if (errorSeverities.length === 0) {
    return buildMetric(
      "error-severity-bounding",
      "safety",
      "Error Severity Bounding",
      1,
      0,
    );
  }
  const violations = errorSeverities.filter((s) => s > maxAllowed).length;
  const score = 1 - violations / errorSeverities.length;
  return buildMetric(
    "error-severity-bounding",
    "safety",
    "Error Severity Bounding",
    score,
    errorSeverities.length,
  );
}

export function measureSafeFailureModes(
  failureOutcomes: readonly ("safe" | "unsafe" | "unknown")[],
): MetricResult {
  if (failureOutcomes.length === 0) {
    return buildMetric(
      "safe-failure-modes",
      "safety",
      "Safe Failure Modes",
      1,
      0,
    );
  }
  const safe = failureOutcomes.filter((o) => o === "safe").length;
  const score = safe / failureOutcomes.length;
  return buildMetric(
    "safe-failure-modes",
    "safety",
    "Safe Failure Modes",
    score,
    failureOutcomes.length,
  );
}

export function aggregateSnapshot(
  agentId: string,
  taskType: string,
  metrics: MetricResult[],
): ReliabilitySnapshot {
  const validScores = metrics
    .filter((m) => m.status !== "unknown")
    .map((m) => m.score);
  const overall_score =
    validScores.length === 0
      ? 0
      : validScores.reduce((a, b) => a + b, 0) / validScores.length;
  const hasFail = metrics.some((m) => m.status === "fail");
  const allPass = metrics.every(
    (m) => m.status === "pass" || m.status === "unknown",
  );

  return ReliabilitySnapshotSchema.parse({
    schema_version: RELIABILITY_VERSION,
    snapshot_id: `snap-${Date.now()}`,
    agent_id: agentId,
    task_type: taskType,
    metrics,
    overall_score,
    overall_status: allPass ? "pass" : hasFail ? "fail" : "partial",
    recorded_at: new Date().toISOString(),
  });
}

export function persistSnapshot(
  snapshot: ReliabilitySnapshot,
  projectDir: string,
): void {
  const historyPath = join(projectDir, ".omg", "reliability", "history.jsonl");
  mkdirSync(dirname(historyPath), { recursive: true });
  appendFileSync(historyPath, JSON.stringify(snapshot) + "\n");
}

function buildMetric(
  metricId: string,
  dimension: MetricDimension,
  name: string,
  score: number,
  sampleCount: number,
  forceStatus?: "pass" | "fail" | "unknown",
): MetricResult {
  const threshold = DEFAULT_THRESHOLDS[metricId] ?? 0.7;
  const status = forceStatus ?? (score >= threshold ? "pass" : "fail");
  return MetricResultSchema.parse({
    metric_id: metricId,
    dimension,
    name,
    score: Math.max(0, Math.min(1, score)),
    threshold,
    status,
    sample_count: sampleCount,
  });
}
