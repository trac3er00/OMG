export type SkepticVerdict = "accept" | "warn" | "reject";

export interface SkepticEvaluation {
  readonly verdict: SkepticVerdict;
  readonly reason: string;
}

const REJECT_PATTERNS: readonly RegExp[] = [/\btrust me\b/i];

export class SkepticCritic {
  evaluate(claim: string, evidence: readonly string[]): SkepticEvaluation {
    const normalizedClaim = claim.trim();
    const validEvidence = evidence.map((item) => item.trim()).filter((item) => item.length > 0);

    if (normalizedClaim.length === 0) {
      return {
        verdict: "warn",
        reason: "Claim text is empty; cannot validate without a concrete assertion.",
      };
    }

    if (REJECT_PATTERNS.some((pattern) => pattern.test(normalizedClaim))) {
      return {
        verdict: "reject",
        reason: "Claim contains an unsupported confidence phrase ('trust me').",
      };
    }

    if (validEvidence.length === 0) {
      return {
        verdict: "warn",
        reason: "Claim lacks evidence pointers; include artifacts or commands to verify.",
      };
    }

    return {
      verdict: "accept",
      reason: `Claim is backed by ${validEvidence.length} evidence pointer(s).`,
    };
  }
}
