import type {
  ProofGateResult,
  EvidenceType,
  ProofScore,
  ProofVerdict,
} from "../interfaces/evidence.js";
import { judgeSingleClaim, type Claim } from "./claim-judge.js";

export interface EvidenceBundle {
  readonly junit?: {
    tests: number;
    failures: number;
    errors: number;
    stale?: boolean;
    generatedAt?: string;
  };
  readonly coverage?: {
    line_rate: number;
    stale?: boolean;
    generatedAt?: string;
  };
  readonly sarif?: { results: unknown[] };
  readonly browser_trace?: unknown;
  readonly test_intent_lock?: { locked: boolean };
  readonly [key: string]: unknown;
}

interface EvidenceFreshnessMeta {
  readonly stale?: boolean;
  readonly generatedAt?: string;
}

export interface ProductionGateResult {
  readonly status: ProofVerdict;
  readonly blockers: readonly string[];
  readonly requiredPrimitives: readonly EvidenceType[];
  readonly evidenceSummary: Readonly<Record<string, unknown>>;
  readonly proofScore: ProofScore;
}

const REQUIRED_PRIMITIVES: readonly EvidenceType[] = ["junit", "coverage"];
const MIN_COVERAGE = 0.7;

function toProofScoreBand(score: number): ProofScore["band"] {
  if (score >= 85) {
    return "complete";
  }
  if (score >= 65) {
    return "strong";
  }
  if (score >= 40) {
    return "developing";
  }
  return "weak";
}

function createProofScore(
  evidence: EvidenceBundle,
  blockers: readonly string[],
  claimVerdict?: ReturnType<typeof judgeSingleClaim>,
): ProofScore {
  const requiredPresent = REQUIRED_PRIMITIVES.filter(
    (primitive) => evidence[primitive] != null,
  ).length;
  const completeness = (requiredPresent / REQUIRED_PRIMITIVES.length) * 45;

  const junitQuality =
    evidence.junit == null
      ? 0
      : evidence.junit.failures === 0 && evidence.junit.errors === 0
        ? 20
        : Math.max(
            0,
            20 - evidence.junit.failures * 8 - evidence.junit.errors * 10,
          );
  const coverageQuality =
    evidence.coverage == null
      ? 0
      : Math.min(20, (evidence.coverage.line_rate / MIN_COVERAGE) * 20);
  const optionalEvidence = Math.min(
    10,
    [evidence.sarif, evidence.browser_trace, evidence.test_intent_lock].filter(
      (value) => value != null,
    ).length * 5,
  );
  const claimContribution =
    claimVerdict == null ? 0 : claimVerdict.proofScore.score * 0.05;
  const penalties = Math.min(45, blockers.length * 15);
  const score = Number(
    Math.max(
      0,
      Math.min(
        100,
        completeness +
          junitQuality +
          coverageQuality +
          optionalEvidence +
          claimContribution -
          penalties,
      ),
    ).toFixed(2),
  );

  return {
    score,
    band: toProofScoreBand(score),
    breakdown: {
      completeness: Number(completeness.toFixed(2)),
      junitQuality: Number(junitQuality.toFixed(2)),
      coverageQuality: Number(coverageQuality.toFixed(2)),
      optionalEvidence: Number(optionalEvidence.toFixed(2)),
      claimContribution: Number(claimContribution.toFixed(2)),
      penalties: Number(penalties.toFixed(2)),
    },
  };
}

export function productionGate(evidence: EvidenceBundle): ProductionGateResult {
  const blockers: string[] = [];

  for (const primitive of REQUIRED_PRIMITIVES) {
    const primitiveEvidence = evidence[primitive] as
      | EvidenceFreshnessMeta
      | undefined;
    if (!(primitive in evidence) || primitiveEvidence == null) {
      blockers.push(`Missing required evidence: ${primitive}`);
      continue;
    }

    if (primitiveEvidence.stale === true) {
      const generatedAtSuffix =
        typeof primitiveEvidence.generatedAt === "string" &&
        primitiveEvidence.generatedAt.length > 0
          ? ` (generatedAt=${primitiveEvidence.generatedAt})`
          : "";
      blockers.push(
        `Stale required evidence: ${primitive}${generatedAtSuffix}`,
      );
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
    proofScore: createProofScore(evidence, blockers),
  };
}

export interface ProofGateInput {
  readonly evidence: EvidenceBundle;
  readonly runId?: string;
  readonly claim?: Claim;
}

export function evaluateProofGate(input: ProofGateInput): ProofGateResult {
  const result = productionGate(input.evidence);

  const blockers = [...result.blockers];
  let claimVerdict: ReturnType<typeof judgeSingleClaim> | undefined;
  if (input.claim) {
    claimVerdict = judgeSingleClaim(input.claim);
    if (claimVerdict.verdict !== "accept") {
      blockers.push(...claimVerdict.reasons);
    }
  }

  return {
    status: blockers.length === 0 ? "pass" : "blocked",
    blockers,
    requiredPrimitives: result.requiredPrimitives,
    evidenceSummary: result.evidenceSummary,
    proofScore: createProofScore(input.evidence, blockers, claimVerdict),
  };
}
