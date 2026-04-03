import {
  createEpistemicState,
  createUncertaintyScore,
  HIGH_CONFIDENCE_THRESHOLD,
  UNCERTAINTY_THRESHOLD,
  type EpistemicState,
  type UncertaintyScore,
} from "./types.js";

export const KNOWN_DOMAINS = new Set([
  "typescript",
  "javascript",
  "python",
  "code-review",
  "security",
  "testing",
  "git",
  "documentation",
]);

export interface EpistemicAssessment {
  readonly state: EpistemicState;
  readonly uncertainty_score: UncertaintyScore;
  readonly novel_domain: boolean;
  readonly flags: readonly string[];
}

export function assessEpistemicState(opts: {
  confidence: number;
  source: UncertaintyScore["source"];
  domain?: string;
  evidence_refs?: string[];
}): EpistemicAssessment {
  const { confidence, source, domain, evidence_refs = [] } = opts;
  const flags: string[] = [];
  let novel_domain = false;

  if (domain != null && !KNOWN_DOMAINS.has(domain.toLowerCase())) {
    flags.push(`novel_domain:${domain}`);
    novel_domain = true;
  }

  if (evidence_refs.length === 0) {
    flags.push("no_evidence");
  }

  const classification =
    confidence >= HIGH_CONFIDENCE_THRESHOLD && evidence_refs.length > 0
      ? ("known" as const)
      : confidence < 0.3 ||
          (evidence_refs.length === 0 && confidence < UNCERTAINTY_THRESHOLD)
        ? ("unknown" as const)
        : ("uncertain" as const);

  const state = createEpistemicState(classification, {
    domain,
    evidence_refs,
    unknown_unknowns_detected: novel_domain,
    flags,
  });

  const score = createUncertaintyScore(confidence, source);

  return {
    state,
    uncertainty_score: score,
    novel_domain,
    flags,
  };
}

export function trackNovelDomain(
  domain: string,
  evidenceCount: number,
): EpistemicAssessment {
  const confidence =
    evidenceCount === 0 ? 0.1 : Math.min(0.6, evidenceCount * 0.15);
  return assessEpistemicState({
    confidence,
    source: "epistemic_state",
    domain,
    evidence_refs: [],
  });
}

export function mergeAssessments(
  assessments: readonly EpistemicAssessment[],
): EpistemicAssessment {
  if (assessments.length === 0) {
    return assessEpistemicState({ confidence: 0, source: "fallback" });
  }

  const avgConfidence =
    assessments.reduce((sum, a) => sum + a.uncertainty_score.value, 0) /
    assessments.length;

  const allEvidenceRefs = [
    ...new Set(assessments.flatMap((a) => [...a.state.evidence_refs])),
  ];
  const novelDomainAssessment = assessments.find((a) => a.novel_domain);
  const domains = assessments
    .map((a) => a.state.domain)
    .filter((d): d is string => d != null);
  const primaryDomain = novelDomainAssessment?.state.domain ?? domains[0];

  return assessEpistemicState({
    confidence: avgConfidence,
    source: "epistemic_state",
    ...(primaryDomain != null ? { domain: primaryDomain } : {}),
    evidence_refs: allEvidenceRefs,
  });
}
