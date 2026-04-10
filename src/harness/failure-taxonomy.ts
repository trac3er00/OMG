import { z } from "zod";
import { appendFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";

export const TAXONOMY_VERSION = "1.0.0";

export type FailureCategory =
  | "context-related"
  | "tool-related"
  | "governance-related"
  | "reliability-related"
  | "reasoning-related"
  | "hallucination-related"
  | "unknown";

export const FailureReportSchema = z.object({
  schema_version: z.literal(TAXONOMY_VERSION),
  failure_id: z.string(),
  category: z.enum([
    "context-related",
    "tool-related",
    "governance-related",
    "reliability-related",
    "reasoning-related",
    "hallucination-related",
    "unknown",
  ]),
  error_message: z.string(),
  root_cause: z.string(),
  remediation: z.string(),
  confidence: z.number().min(0).max(1),
  test_file: z.string().optional(),
  detected_at: z.string(),
});
export type FailureReport = z.infer<typeof FailureReportSchema>;

const CONTEXT_PATTERNS = [
  /context.*(loss|lost|expired|stale|corrupt)/i,
  /context.*(saturation|overflow|limit)/i,
  /reconstruct/i,
  /workspace.*(state|corrupt)/i,
  /checkpoint.*fail/i,
];

const TOOL_PATTERNS = [
  /timeout.*ms/i,
  /tool.*error/i,
  /ENOENT|EACCES|EPERM/,
  /command.*not.*found/i,
  /spawn.*fail/i,
  /circuit.*(open|breaker)/i,
];

const GOVERNANCE_PATTERNS = [
  /governance.*block/i,
  /approval.*required/i,
  /signed.*approval/i,
  /attestation.*required/i,
  /policy.*den(y|ied)/i,
];

const RELIABILITY_PATTERNS = [
  /reliability.*below.*threshold/i,
  /calibration.*(drift|fail|uncalibrated)/i,
  /consistency.*score/i,
  /predictability.*degrad/i,
  /safe failure.*fail/i,
];

const HALLUCINATION_PATTERNS = [
  /file.*does.*not.*exist/i,
  /module.*not.*found/i,
  /cannot.*import/i,
  /undefined.*is.*not.*a.*function/i,
  /fabricat/i,
  /non.?existent/i,
];

const REASONING_PATTERNS = [
  /logic.*error/i,
  /assertion.*fail/i,
  /expected.*received/i,
  /incorrect.*assumption/i,
  /invalid.*state/i,
];

function classifyError(errorMessage: string): {
  category: FailureCategory;
  confidence: number;
  root_cause: string;
  remediation: string;
} {
  for (const pattern of CONTEXT_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "context-related",
        confidence: 0.85,
        root_cause: "Context loss or corruption during task execution",
        remediation: "Restore from checkpoint; increase checkpoint frequency",
      };
    }
  }

  for (const pattern of TOOL_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "tool-related",
        confidence: 0.9,
        root_cause: "Tool execution failure or timeout",
        remediation:
          "Retry with backoff; check tool availability and permissions",
      };
    }
  }

  for (const pattern of GOVERNANCE_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "governance-related",
        confidence: 0.88,
        root_cause: "Governance approval or policy gate blocked execution",
        remediation:
          "Refresh approvals, attestations, and required policy evidence",
      };
    }
  }

  for (const pattern of RELIABILITY_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "reliability-related",
        confidence: 0.82,
        root_cause:
          "Reliability verification detected unstable or degraded behavior",
        remediation:
          "Re-run calibration and inspect consistency, predictability, and safety metrics",
      };
    }
  }

  for (const pattern of HALLUCINATION_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "hallucination-related",
        confidence: 0.8,
        root_cause:
          "AI referenced non-existent resource or fabricated information",
        remediation:
          "Verify all references before use; enable epistemic state tracking",
      };
    }
  }

  for (const pattern of REASONING_PATTERNS) {
    if (pattern.test(errorMessage)) {
      return {
        category: "reasoning-related",
        confidence: 0.75,
        root_cause: "Logic error or incorrect reasoning in task execution",
        remediation:
          "Review task decomposition; enable multi-perspective verification",
      };
    }
  }

  return {
    category: "unknown",
    confidence: 0.3,
    root_cause: "Unclassified failure",
    remediation: "Manual investigation required",
  };
}

export function classifyFailure(opts: {
  error_message: string;
  test_file?: string;
  failure_id?: string;
}): FailureReport {
  const classified = classifyError(opts.error_message);
  return FailureReportSchema.parse({
    schema_version: TAXONOMY_VERSION,
    failure_id: opts.failure_id ?? `fail-${Date.now()}`,
    category: classified.category,
    error_message: opts.error_message,
    root_cause: classified.root_cause,
    remediation: classified.remediation,
    confidence: classified.confidence,
    test_file: opts.test_file,
    detected_at: new Date().toISOString(),
  });
}

export function persistFailureReport(
  report: FailureReport,
  projectDir: string,
): void {
  const failuresPath = join(projectDir, ".omg", "harness", "failures.jsonl");
  mkdirSync(dirname(failuresPath), { recursive: true });
  appendFileSync(failuresPath, JSON.stringify(report) + "\n");
}

export function summarizeTaxonomy(
  reports: readonly FailureReport[],
): Record<FailureCategory, number> {
  const summary: Record<FailureCategory, number> = {
    "context-related": 0,
    "tool-related": 0,
    "governance-related": 0,
    "reliability-related": 0,
    "reasoning-related": 0,
    "hallucination-related": 0,
    unknown: 0,
  };
  for (const r of reports) {
    summary[r.category]++;
  }
  return summary;
}
