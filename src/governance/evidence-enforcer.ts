export interface Claim {
  readonly type: string;
  readonly evidence: Record<string, unknown> | null | undefined;
  readonly claimedBy?: string;
  readonly timestamp?: string;
}

export interface ClaimValidationResult {
  readonly valid: boolean;
  readonly reason: string;
  readonly evidenceFound: boolean;
  readonly requiredEvidence: string[];
}

const REQUIRED_EVIDENCE_KEYS: Readonly<Record<string, string[]>> = {
  completion: ["testOutput", "files"],
  fetch_complete: ["content"],
  build_success: ["exitCode"],
  deployment: ["environment", "version"],
};

export function validateClaim(claim: Claim): ClaimValidationResult {
  if (!claim.evidence || Object.keys(claim.evidence).length === 0) {
    return {
      valid: false,
      reason: "evidence required: no evidence provided for claim",
      evidenceFound: false,
      requiredEvidence: REQUIRED_EVIDENCE_KEYS[claim.type] ?? ["evidence"],
    };
  }

  const requiredKeys = REQUIRED_EVIDENCE_KEYS[claim.type] ?? [];
  const missingKeys = requiredKeys.filter((key) => !(key in claim.evidence!));

  if (missingKeys.length > 0) {
    return {
      valid: false,
      reason: `evidence required: missing required evidence fields: ${missingKeys.join(", ")}`,
      evidenceFound: true,
      requiredEvidence: missingKeys,
    };
  }

  return {
    valid: true,
    reason: "claim validated with sufficient evidence",
    evidenceFound: true,
    requiredEvidence: [],
  };
}
