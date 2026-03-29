export type EvidenceType = "junit" | "coverage" | "sarif" | "browser_trace" | "proof_chain" | "test_intent_lock";
export type ProofVerdict = "pass" | "fail" | "blocked" | "pending";

export interface EvidenceProfile {
  readonly required: readonly EvidenceType[];
  readonly optional: readonly EvidenceType[];
  readonly minCoverage?: number;
  readonly maxAge?: number;
}

export interface ProofGateResult {
  readonly status: ProofVerdict;
  readonly blockers: readonly string[];
  readonly requiredPrimitives: readonly EvidenceType[];
  readonly evidenceSummary: Readonly<Record<string, unknown>>;
}

export interface ClaimVerdict {
  readonly verdict: "accept" | "reject" | "warn";
  readonly reasons: readonly string[];
  readonly evidenceSummary: Readonly<Record<string, unknown>>;
  readonly confidence: number;
}

export interface Finding {
  readonly id: string;
  readonly severity: "critical" | "high" | "medium" | "low" | "info";
  readonly message: string;
  readonly path: string;
  readonly line?: number;
  readonly waived: boolean;
  readonly waiverReason?: string;
}
