import { z } from "zod";

export const METACOGNITIVE_VERSION = "1.0.0";

export const UncertaintyScoreSchema = z.object({
  value: z.number().min(0).max(1),
  source: z.enum([
    "claim_judge",
    "evidence_count",
    "epistemic_state",
    "voting",
    "fallback",
  ]),
  timestamp: z.string().datetime().optional(),
});
export type UncertaintyScore = z.infer<typeof UncertaintyScoreSchema>;

export const EpistemicStateSchema = z.object({
  classification: z.enum(["known", "unknown", "uncertain"]),
  domain: z.string().optional(),
  evidence_refs: z.array(z.string()),
  unknown_unknowns_detected: z.boolean(),
  flags: z.array(z.string()),
});
export type EpistemicState = z.infer<typeof EpistemicStateSchema>;

export const VerificationRequestSchema = z.object({
  trigger_reason: z.enum([
    "low_confidence",
    "novel_domain",
    "high_stakes",
    "explicit",
  ]),
  claim: z.string(),
  uncertainty_score: UncertaintyScoreSchema,
  perspective_count: z.number().int().min(2).max(5).default(3),
});
export type VerificationRequest = z.infer<typeof VerificationRequestSchema>;

export const MetacognitiveReportSchema = z.object({
  schema_version: z.literal(METACOGNITIVE_VERSION),
  uncertainty_score: UncertaintyScoreSchema,
  epistemic_state: EpistemicStateSchema,
  verification_triggered: z.boolean(),
  verification_request: VerificationRequestSchema.optional(),
  final_confidence: z.number().min(0).max(1),
  human_auditable_evidence: z.array(z.string()),
  generated_at: z.string().datetime(),
});
export type MetacognitiveReport = z.infer<typeof MetacognitiveReportSchema>;

export const UNCERTAINTY_THRESHOLD = 0.7;
export const HIGH_CONFIDENCE_THRESHOLD = 0.9;

export function createUncertaintyScore(
  value: number,
  source: UncertaintyScore["source"],
): UncertaintyScore {
  return UncertaintyScoreSchema.parse({
    value: Math.max(0, Math.min(1, value)),
    source,
    timestamp: new Date().toISOString(),
  });
}

export function shouldTriggerVerification(score: UncertaintyScore): boolean {
  return score.value < UNCERTAINTY_THRESHOLD;
}

export function createEpistemicState(
  classification: EpistemicState["classification"],
  opts: Partial<Omit<EpistemicState, "classification">> = {},
): EpistemicState {
  return EpistemicStateSchema.parse({
    classification,
    domain: opts.domain,
    evidence_refs: opts.evidence_refs ?? [],
    unknown_unknowns_detected: opts.unknown_unknowns_detected ?? false,
    flags: opts.flags ?? [],
  });
}
