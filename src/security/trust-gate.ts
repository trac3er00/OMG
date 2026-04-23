import type { TrustTier } from "../interfaces/state.js";
import { getTrustScore } from "./untrusted-content.js";

export interface TrustGateResult {
  readonly content: string;
  readonly warnings: string[];
  readonly trustScore: number;
  readonly tier: TrustTier;
}

const VALID_TIERS: ReadonlySet<string> = new Set([
  "local",
  "balanced",
  "research",
  "browser",
]);

export function applyTrustGate(
  content: string,
  tier: TrustTier | string,
): TrustGateResult {
  const tierStr = String(tier).toLowerCase();
  if (!VALID_TIERS.has(tierStr)) {
    throw new Error(
      `Invalid trust tier: '${tier}'. Valid tiers: local, balanced, research, browser`,
    );
  }
  const validTier = tierStr as TrustTier;
  const trustScore = getTrustScore(validTier);
  const warnings: string[] = [];

  if (trustScore === 0.0) {
    warnings.push(
      `Content from '${validTier}' tier has zero trust score - treat as untrusted external content`,
    );
    warnings.push(
      "Verify content does not contain injection patterns before using",
    );
  } else if (trustScore < 1.0) {
    warnings.push(
      `Content from '${validTier}' tier has partial trust score: ${trustScore}`,
    );
  }

  return {
    content: String(content ?? ""),
    warnings,
    trustScore,
    tier: validTier,
  };
}
