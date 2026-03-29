import type { EvidenceProfile } from "../interfaces/evidence.js";

export type EvidenceProfileName = "default" | "minimal" | "full" | "tdd" | "security";

const PROFILES: Record<EvidenceProfileName, EvidenceProfile> = {
  minimal: {
    required: ["junit"],
    optional: [],
  },
  default: {
    required: ["junit", "coverage"],
    optional: ["sarif", "browser_trace"],
    minCoverage: 0.7,
  },
  tdd: {
    required: ["junit", "coverage"],
    optional: [],
    minCoverage: 0.8,
  },
  full: {
    required: ["junit", "coverage", "sarif"],
    optional: ["browser_trace"],
    minCoverage: 0.8,
  },
  security: {
    required: ["junit", "sarif"],
    optional: ["coverage"],
  },
};

export function getEvidenceProfile(name: EvidenceProfileName | string): EvidenceProfile {
  return PROFILES[name as EvidenceProfileName] ?? PROFILES.default;
}

export function validateEvidenceAgainstProfile(
  evidence: ReadonlyArray<{ type: string; valid: boolean }>,
  profileName: EvidenceProfileName | string,
): { valid: boolean; missing: string[]; invalid: string[] } {
  const profile = getEvidenceProfile(profileName);
  const provided = new Map<string, boolean>();
  for (const e of evidence) {
    provided.set(e.type, e.valid);
  }

  const missing: string[] = [];
  const invalid: string[] = [];

  for (const req of profile.required) {
    if (!provided.has(req)) {
      missing.push(req);
    } else if (provided.get(req) === false) {
      invalid.push(req);
    }
  }

  return {
    valid: missing.length === 0 && invalid.length === 0,
    missing,
    invalid,
  };
}
