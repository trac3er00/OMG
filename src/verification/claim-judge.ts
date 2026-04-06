import type { ClaimVerdict, ProofScore } from "../interfaces/evidence.js";
import {
  evaluateWithCompensators,
  type CompensatorInput,
} from "../compensators/pipeline.js";

export interface EvidenceRef {
  readonly type: "junit" | "coverage" | "sarif" | "browser_trace" | string;
  readonly path?: string;
  readonly valid?: boolean;
}

export interface Claim {
  readonly text: string;
  readonly evidence: readonly EvidenceRef[];
  readonly category?: string;
  readonly compensatorInput?: CompensatorInput;
}

export interface BatchResult {
  readonly results: readonly ClaimVerdict[];
  readonly aggregateVerdict: "accept" | "reject" | "warn" | "pending";
  readonly totalClaims: number;
  readonly acceptedCount: number;
  readonly rejectedCount: number;
}

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

function createClaimProofScore(claim: Claim): ProofScore {
  const totalEvidence = claim.evidence.length;
  const validEvidence = claim.evidence.filter((e) => e.valid !== false);
  const invalidEvidence = totalEvidence - validEvidence.length;
  const uniqueTypes = new Set(validEvidence.map((e) => e.type)).size;
  const pathBackedEvidence = validEvidence.filter(
    (e) => typeof e.path === "string" && e.path.length > 0,
  ).length;
  const completeness = Math.min(40, totalEvidence * 20);
  const validity =
    totalEvidence === 0 ? 0 : Math.max(0, 35 - invalidEvidence * 20);
  const diversity = Math.min(15, uniqueTypes * 7.5);
  const traceability = Math.min(10, pathBackedEvidence * 5);
  const compensator = claim.compensatorInput ? 5 : 0;
  const score = Number(
    Math.max(
      0,
      Math.min(
        100,
        completeness + validity + diversity + traceability + compensator,
      ),
    ).toFixed(2),
  );

  return {
    score,
    band: toProofScoreBand(score),
    breakdown: {
      completeness: Number(completeness.toFixed(2)),
      validity: Number(validity.toFixed(2)),
      diversity: Number(diversity.toFixed(2)),
      traceability: Number(traceability.toFixed(2)),
      compensator: Number(compensator.toFixed(2)),
    },
  };
}

export function judgeSingleClaim(claim: Claim): ClaimVerdict {
  const proofScore = createClaimProofScore(claim);

  if (claim.evidence.length === 0) {
    return {
      verdict: "reject",
      reasons: ["No supporting evidence provided for claim"],
      evidenceSummary: {},
      confidence: 0.1,
      proofScore,
    };
  }

  const invalidEvidence = claim.evidence.filter((e) => e.valid === false);
  if (invalidEvidence.length > 0) {
    return {
      verdict: "reject",
      reasons: [
        `Invalid evidence: ${invalidEvidence.map((e) => e.type).join(", ")}`,
      ],
      evidenceSummary: { invalid: invalidEvidence.map((e) => e.type) },
      confidence: 0.2,
      proofScore,
    };
  }

  const validEvidence = claim.evidence.filter((e) => e.valid !== false);

  if (claim.compensatorInput) {
    const compensatorResult = evaluateWithCompensators(claim.compensatorInput);
    if (compensatorResult.verdict === "REJECT") {
      return {
        verdict: "reject",
        reasons: [
          "Compensator pipeline rejected claim",
          ...compensatorResult.reasons,
        ],
        evidenceSummary: {
          types: validEvidence.map((e) => e.type),
          compensators: compensatorResult.checks,
        },
        confidence: 0.2,
        proofScore,
      };
    }
  }

  return {
    verdict: "accept",
    reasons: [`Supported by ${validEvidence.length} evidence item(s)`],
    evidenceSummary: { types: validEvidence.map((e) => e.type) },
    confidence: Math.min(0.9 + validEvidence.length * 0.02, 1.0),
    proofScore,
  };
}

export function judgeClaimBatch(claims: readonly Claim[]): BatchResult {
  if (claims.length === 0) {
    return {
      results: [],
      aggregateVerdict: "pending",
      totalClaims: 0,
      acceptedCount: 0,
      rejectedCount: 0,
    };
  }

  const results = claims.map(judgeSingleClaim);
  const acceptedCount = results.filter((r) => r.verdict === "accept").length;
  const rejectedCount = results.filter((r) => r.verdict === "reject").length;

  let aggregateVerdict: "accept" | "reject" | "warn" | "pending";
  if (rejectedCount > 0) {
    aggregateVerdict = "reject";
  } else if (acceptedCount === claims.length) {
    aggregateVerdict = "accept";
  } else {
    aggregateVerdict = "warn";
  }

  return {
    results,
    aggregateVerdict,
    totalClaims: claims.length,
    acceptedCount,
    rejectedCount,
  };
}
