import type { ProofGateResult, EvidenceType, ProofVerdict } from "../interfaces/evidence.js";

export interface EvidenceBundle {
  readonly junit?: { tests: number; failures: number; errors: number };
  readonly coverage?: { line_rate: number };
  readonly sarif?: { results: unknown[] };
  readonly browser_trace?: unknown;
  readonly test_intent_lock?: { locked: boolean };
  readonly [key: string]: unknown;
}

export interface ProductionGateResult {
  readonly status: ProofVerdict;
  readonly blockers: readonly string[];
  readonly requiredPrimitives: readonly EvidenceType[];
  readonly evidenceSummary: Readonly<Record<string, unknown>>;
}

const REQUIRED_PRIMITIVES: readonly EvidenceType[] = ["junit", "coverage"];
const MIN_COVERAGE = 0.7;

export function productionGate(evidence: EvidenceBundle): ProductionGateResult {
  const blockers: string[] = [];

  for (const primitive of REQUIRED_PRIMITIVES) {
    if (!(primitive in evidence) || evidence[primitive] == null) {
      blockers.push(`Missing required evidence: ${primitive}`);
    }
  }

  if (evidence.junit) {
    const j = evidence.junit;
    if (j.failures > 0) {
      blockers.push(`Test failures: ${j.failures} test(s) failed`);
    }
    if (j.errors > 0) {
      blockers.push(`Test errors: ${j.errors} error(s)`);
    }
  }

  if (evidence.coverage) {
    const c = evidence.coverage;
    if (c.line_rate < MIN_COVERAGE) {
      blockers.push(
        `Coverage below threshold: ${(c.line_rate * 100).toFixed(1)}% < ${MIN_COVERAGE * 100}%`,
      );
    }
  }

  return {
    status: blockers.length === 0 ? "pass" : "blocked",
    blockers,
    requiredPrimitives: REQUIRED_PRIMITIVES,
    evidenceSummary: evidence as Readonly<Record<string, unknown>>,
  };
}

export interface ProofGateInput {
  readonly evidence: EvidenceBundle;
  readonly runId?: string;
}

export function evaluateProofGate(input: ProofGateInput): ProofGateResult {
  const result = productionGate(input.evidence);
  return {
    status: result.status,
    blockers: result.blockers,
    requiredPrimitives: result.requiredPrimitives,
    evidenceSummary: result.evidenceSummary,
  };
}
