/**
 * Trust scoring system for external sources.
 *
 * TypeScript trust tier system for v2.7.0.
 * Python TrustTier enum (LOCAL/BALANCED/RESEARCH/BROWSER) remains unchanged.
 * TypeScript adapter translates at boundary: UNTRUSTED → Python BROWSER.
 */

import type { FirewallConfig } from "./external-firewall.js";

/**
 * TypeScript trust tiers for external source scoring.
 * Note: Python enum unchanged in v2.7.0.
 */
export const enum TrustTier {
  /** Local files - full trust (1.0) */
  LOCAL = "LOCAL",
  /** Known-good domains - high trust (0.8) - NEW in v2.7.0 */
  VERIFIED = "VERIFIED",
  /** General web search results - partial trust (0.3) */
  RESEARCH = "RESEARCH",
  /** Unknown sources, user-provided URLs - no trust (0.0) */
  UNTRUSTED = "UNTRUSTED",
}

/** Numeric trust scores for each tier */
export const TRUST_SCORES: Readonly<Record<TrustTier, number>> = {
  [TrustTier.LOCAL]: 1.0,
  [TrustTier.VERIFIED]: 0.8,
  [TrustTier.RESEARCH]: 0.3,
  [TrustTier.UNTRUSTED]: 0.0,
};

export interface TrustScore {
  readonly tier: TrustTier;
  readonly score: number;
  readonly reason: string;
  readonly domain: string;
}

export interface TrustScoringConfig {
  readonly additionalVerifiedDomains?: readonly string[];
}

/**
 * Default verified domains that receive VERIFIED trust tier.
 * These are official documentation and package registry domains.
 */
const DEFAULT_VERIFIED_DOMAINS: readonly string[] = [
  "docs.",
  "github.com",
  "npmjs.com",
  "pypi.org",
  "developer.mozilla.org",
  "developer.apple.com",
  "developers.google.com",
  "learn.microsoft.com",
  "nodejs.org",
  "bun.sh",
];

/**
 * Schemes that indicate untrusted sources.
 */
const UNTRUSTED_SCHEMES: readonly string[] = ["data:", "javascript:", "blob:"];

/**
 * Extract domain from URL string.
 * Returns empty string for invalid URLs.
 */
function extractDomain(urlString: string): string {
  try {
    const url = new URL(urlString);
    return url.hostname.toLowerCase();
  } catch {
    return "";
  }
}

/**
 * Check if a URL uses a local file scheme.
 */
function isLocalUrl(urlString: string): boolean {
  const lower = urlString.toLowerCase().trim();
  if (lower.startsWith("file://")) {
    return true;
  }
  // Check for absolute paths (Unix or Windows)
  if (lower.startsWith("/") || /^[a-z]:\\/i.test(lower)) {
    return true;
  }
  // Check for relative paths within cwd
  if (!lower.includes("://") && !lower.includes(":")) {
    return true;
  }
  return false;
}

/**
 * Check if a URL uses an untrusted scheme.
 */
function isUntrustedScheme(urlString: string): boolean {
  const lower = urlString.toLowerCase().trim();
  return UNTRUSTED_SCHEMES.some((scheme) => lower.startsWith(scheme));
}

/**
 * Check if a domain matches a verified domain pattern.
 * Patterns can be:
 * - Exact match: "github.com"
 * - Subdomain prefix: "docs." matches "docs.python.org"
 * - Partial match: "nodejs.org" matches "nodejs.org/en/docs"
 */
function matchesVerifiedDomain(
  domain: string,
  verifiedDomains: readonly string[],
): string | null {
  for (const pattern of verifiedDomains) {
    // Subdomain prefix pattern (e.g., "docs.")
    if (pattern.endsWith(".") && domain.startsWith(pattern)) {
      return pattern;
    }
    // Exact match or subdomain match
    if (domain === pattern || domain.endsWith(`.${pattern}`)) {
      return pattern;
    }
  }
  return null;
}

/**
 * Score a URL based on its domain.
 */
export function scoreDomain(
  url: string,
  config?: TrustScoringConfig,
): TrustScore {
  const urlString = String(url ?? "").trim();

  // Handle empty or whitespace-only URLs
  if (!urlString) {
    return {
      tier: TrustTier.UNTRUSTED,
      score: TRUST_SCORES[TrustTier.UNTRUSTED],
      reason: "Empty URL",
      domain: "",
    };
  }

  // Check for local file URLs first
  if (isLocalUrl(urlString)) {
    return {
      tier: TrustTier.LOCAL,
      score: TRUST_SCORES[TrustTier.LOCAL],
      reason: "Local file path",
      domain: "local",
    };
  }

  // Check for untrusted schemes
  if (isUntrustedScheme(urlString)) {
    return {
      tier: TrustTier.UNTRUSTED,
      score: TRUST_SCORES[TrustTier.UNTRUSTED],
      reason: "Untrusted URL scheme",
      domain: "",
    };
  }

  // Extract domain
  const domain = extractDomain(urlString);
  if (!domain) {
    return {
      tier: TrustTier.UNTRUSTED,
      score: TRUST_SCORES[TrustTier.UNTRUSTED],
      reason: "Invalid URL format",
      domain: "",
    };
  }

  // Build verified domains list
  const verifiedDomains = [
    ...DEFAULT_VERIFIED_DOMAINS,
    ...(config?.additionalVerifiedDomains ?? []),
  ];

  // Check for verified domain match
  const matchedPattern = matchesVerifiedDomain(domain, verifiedDomains);
  if (matchedPattern) {
    return {
      tier: TrustTier.VERIFIED,
      score: TRUST_SCORES[TrustTier.VERIFIED],
      reason: `Verified domain matching pattern: ${matchedPattern}`,
      domain,
    };
  }

  // Default to RESEARCH tier for HTTP(S) URLs
  const lower = urlString.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://")) {
    return {
      tier: TrustTier.RESEARCH,
      score: TRUST_SCORES[TrustTier.RESEARCH],
      reason: "General web URL",
      domain,
    };
  }

  // Unknown schemes are untrusted
  return {
    tier: TrustTier.UNTRUSTED,
    score: TRUST_SCORES[TrustTier.UNTRUSTED],
    reason: "Unknown URL scheme",
    domain,
  };
}

/**
 * Score a source string. Delegates to scoreDomain for URLs,
 * treats plain text as untrusted user input.
 */
export function scoreSource(
  source: string,
  config?: TrustScoringConfig,
): TrustScore {
  const sourceString = String(source ?? "").trim();

  // Handle empty sources
  if (!sourceString) {
    return {
      tier: TrustTier.UNTRUSTED,
      score: TRUST_SCORES[TrustTier.UNTRUSTED],
      reason: "Empty source",
      domain: "",
    };
  }

  // Check if it looks like a URL
  if (
    sourceString.includes("://") ||
    sourceString.startsWith("/") ||
    sourceString.startsWith("file:") ||
    /^[a-z]:\\/i.test(sourceString)
  ) {
    return scoreDomain(sourceString, config);
  }

  // Plain text without URL-like patterns is user-provided
  return {
    tier: TrustTier.UNTRUSTED,
    score: TRUST_SCORES[TrustTier.UNTRUSTED],
    reason: "User-provided source string",
    domain: "",
  };
}

/**
 * Get firewall configuration based on trust score.
 *
 * Lower trust → stricter sanitization:
 * - LOCAL: Allow raw (no sanitization)
 * - VERIFIED: 100KB limit, light sanitization
 * - RESEARCH: 50KB limit, full sanitization
 * - UNTRUSTED: 10KB limit, strict sanitization
 */
export function getFirewallConfigForTrust(trust: TrustScore): FirewallConfig {
  switch (trust.tier) {
    case TrustTier.LOCAL:
      return {
        allowExternalRaw: true,
      };

    case TrustTier.VERIFIED:
      return {
        allowExternalRaw: false,
        maxContentBytes: 102_400, // 100KB
      };

    case TrustTier.RESEARCH:
      return {
        allowExternalRaw: false,
        maxContentBytes: 51_200, // 50KB
      };

    case TrustTier.UNTRUSTED:
      return {
        allowExternalRaw: false,
        maxContentBytes: 10_240, // 10KB
      };

    default:
      // Fail-closed: treat unknown tiers as untrusted
      return {
        allowExternalRaw: false,
        maxContentBytes: 10_240,
      };
  }
}
