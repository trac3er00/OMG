import { nowIso } from "../runtime/common.ts";
import { validateJobRequest } from "./policies.ts";

export function runPipeline(job: Record<string, unknown>) {
  const validation = validateJobRequest(job);
  if (!validation.ok) {
    return {
      status: "blocked",
      stage: "policy",
      reason: validation.reason,
      published: false,
      evaluation_report: null
    };
  }

  const targetMetric = Number(job.target_metric ?? 0.8);
  const simulatedMetric = Number(job.simulated_metric ?? targetMetric);
  const passed = simulatedMetric >= targetMetric;

  const stages = [
    { name: "data_prepare", status: "ok" },
    { name: "synthetic_refine", status: "ok" },
    { name: "train_distill", status: "ok" },
    { name: "evaluate", status: passed ? "ok" : "fail" },
    { name: "regression_test", status: passed ? "ok" : "fail" }
  ];

  const evaluation_report = {
    created_at: nowIso(),
    metric: simulatedMetric,
    target_metric: targetMetric,
    passed,
    notes: String(job.evaluation_notes || "")
  };

  if (!passed) {
    return {
      status: "failed_evaluation",
      stage: "evaluate",
      stages,
      published: false,
      evaluation_report
    };
  }

  return {
    status: "ready",
    stage: "complete",
    stages,
    published: false,
    evaluation_report
  };
}

export function publishArtifact(result: Record<string, unknown>) {
  const report =
    result.evaluation_report && typeof result.evaluation_report === "object" && !Array.isArray(result.evaluation_report)
      ? (result.evaluation_report as Record<string, unknown>)
      : null;

  if (!report || report.passed !== true) {
    return {
      status: "blocked",
      reason: "evaluation report missing or not passed",
      published: false
    };
  }

  return {
    ...result,
    status: "published",
    published: true,
    published_at: nowIso()
  };
}
