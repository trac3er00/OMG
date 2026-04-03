import {
  createUncertaintyScore,
  shouldTriggerVerification,
  type MetacognitiveReport,
  MetacognitiveReportSchema,
  METACOGNITIVE_VERSION,
} from "./types.js";
import {
  assessEpistemicState,
  type EpistemicAssessment,
} from "./epistemic-tracker.js";
import {
  createPerspectiveOutput,
  shouldActivateSoT,
} from "../debate/perspectives.js";
import { conductVote } from "../debate/voting.js";

export interface PipelineInput {
  readonly claim: string;
  readonly confidence: number;
  readonly evidence_refs: string[];
  readonly domain?: string;
  readonly is_high_stakes?: boolean;
  readonly task_complexity?: 1 | 2 | 3 | 4 | 5;
}

export interface PipelineOutput {
  readonly report: MetacognitiveReport;
  readonly epistemic_assessment: EpistemicAssessment;
  readonly verification_performed: boolean;
  readonly token_cost_multiplier: number;
}

const BASELINE_TOKEN_COST = 100;

export function runMetacognitivePipeline(input: PipelineInput): PipelineOutput {
  const uncertainty_score = createUncertaintyScore(
    input.confidence,
    "claim_judge",
  );
  const epistemic_assessment = assessEpistemicState({
    confidence: input.confidence,
    source: "claim_judge",
    ...(input.domain != null ? { domain: input.domain } : {}),
    evidence_refs: input.evidence_refs,
  });

  let verification_performed = false;
  let token_cost_multiplier = 1.0;
  let final_confidence = input.confidence;

  const triggerVerification = shouldTriggerVerification(uncertainty_score);
  const sotDecision = shouldActivateSoT({
    complexity_level: input.task_complexity ?? 3,
    ...(input.domain != null ? { domain: input.domain } : {}),
    is_high_stakes: input.is_high_stakes ?? false,
  });

  if (triggerVerification || sotDecision.should_activate) {
    const proposer = createPerspectiveOutput("proposer", input.claim, {
      confidence: input.confidence,
      evidence_refs: input.evidence_refs,
    } as never);
    const critic = createPerspectiveOutput(
      "critic",
      `Reviewing: ${input.claim}`,
      {
        confidence: Math.max(0.1, input.confidence - 0.2),
      } as never,
    );
    const redTeam = createPerspectiveOutput(
      "red-team",
      `Risk analysis: ${input.claim}`,
      {
        confidence: Math.max(0.1, input.confidence - 0.3),
      } as never,
    );

    const votingResult = conductVote(
      [proposer, critic, redTeam],
      BASELINE_TOKEN_COST,
      BASELINE_TOKEN_COST,
    );

    verification_performed = true;
    token_cost_multiplier = Math.min(3.0, votingResult.token_cost_multiplier);
    final_confidence = votingResult.aggregate_confidence;
  }

  const evidenceRefs = [
    ...(epistemic_assessment.state.evidence_refs ?? []),
    `epistemic:${epistemic_assessment.state.classification}`,
  ];

  const report = MetacognitiveReportSchema.parse({
    schema_version: METACOGNITIVE_VERSION,
    uncertainty_score: {
      value: uncertainty_score.value,
      source: uncertainty_score.source,
    },
    epistemic_state: epistemic_assessment.state,
    verification_triggered: verification_performed,
    ...(verification_performed
      ? {
          verification_request: {
            trigger_reason: shouldTriggerVerification(uncertainty_score)
              ? "low_confidence"
              : "explicit",
            claim: input.claim,
            uncertainty_score: {
              value: uncertainty_score.value,
              source: uncertainty_score.source,
            },
            perspective_count: 3,
          },
        }
      : {}),
    final_confidence,
    human_auditable_evidence: evidenceRefs,
    generated_at: new Date().toISOString(),
  });

  return {
    report,
    epistemic_assessment,
    verification_performed,
    token_cost_multiplier,
  };
}
