import type { ClaimVerdict } from "../interfaces/evidence.js";
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

export function judgeSingleClaim(claim: Claim): ClaimVerdict {
  if (claim.evidence.length === 0) {
    return {
      verdict: "reject",
      reasons: ["No supporting evidence provided for claim"],
      evidenceSummary: {},
      confidence: 0.1,
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
      };
    }
  }

  return {
    verdict: "accept",
    reasons: [`Supported by ${validEvidence.length} evidence item(s)`],
    evidenceSummary: { types: validEvidence.map((e) => e.type) },
    confidence: Math.min(0.9 + validEvidence.length * 0.02, 1.0),
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
