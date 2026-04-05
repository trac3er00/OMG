import type { TrustTier } from "../interfaces/state.js";

const TRUST_SCORES: Readonly<Record<TrustTier, number>> = {
  local: 1.0,
  balanced: 0.7,
  research: 0.0,
  browser: 0.0,
};

// Security: injection detection patterns — quarantine matching lines
const INSTRUCTION_PATTERNS: readonly RegExp[] = [
  /ignore\s+(all\s+)?previous\s+(instructions?|rules?|constraints?)/i,
  /override\s+(system|instructions?|rules?)/i,
  /new\s+task:/i,
  /you\s+are\s+now\s+(a\s+)?(different|new|another|free)/i,
  /forget\s+(everything|all)\s+(you\s+)?know/i,
  /disregard\s+your\s+(previous|prior|earlier)\s+(instructions?|programming)/i,
  /^SYSTEM:/m,
  /^ASSISTANT:/m,
  /act\s+as\s+if\s+(you\s+are|you're)\s+(a\s+)?(?:evil|unrestricted|jailbroken)/i,
];

export interface QuarantineResult {
  readonly sanitized: string;
  readonly quarantined: readonly string[];
  readonly hitCount: number;
}

export function getTrustScore(tier: TrustTier): number {
  return TRUST_SCORES[tier];
}

export function quarantineInstructions(content: string): QuarantineResult {
  const quarantined: string[] = [];
  const sanitizedLines: string[] = [];

  for (const line of content.split("\n")) {
    let matched = false;
    for (const pattern of INSTRUCTION_PATTERNS) {
      if (pattern.test(line)) {
        quarantined.push(line.trim());
        matched = true;
        break;
      }
    }
    if (!matched) {
      sanitizedLines.push(line);
    }
  }

  return {
    sanitized: sanitizedLines.join("\n").trim(),
    quarantined,
    hitCount: quarantined.length,
  };
}

export function scoreTrustTier(tier: TrustTier): number {
  return getTrustScore(tier);
}
