import { z } from "zod";
import { ContextEngineeringSystem } from "../context/context-engineering.js";
import { type CompactCanonicalState } from "../context/workspace-reconstruction.js";
import { type AgentCard } from "../orchestration/a2a.js";
import { type VotingResult, conductVote } from "../debate/voting.js";
import { formConsensus } from "../debate/consensus.js";
import {
  shouldActivateSoT,
  createPerspectiveOutput,
} from "../debate/perspectives.js";
import { GovernanceGraphRuntime } from "../governance/graph.js";
import { GovernanceLedger } from "../governance/ledger.js";
import { runCollusionDetection } from "../governance/collusion.js";
import {
  aggregateSnapshot,
  type MetricResult,
  measureSameInputConsistency,
} from "../reliability/metrics.js";
import {
  runMetacognitivePipeline,
  type PipelineOutput,
} from "../metacognitive/pipeline.js";

export const FRONTIER_PIPELINE_VERSION = "1.0.0";

export const FrontierPipelineResultSchema = z.object({
  schema_version: z.literal(FRONTIER_PIPELINE_VERSION),
  session_id: z.string(),
  context_pressure: z.number().min(0).max(1),
  debate_activated: z.boolean(),
  governance_transitions: z.array(z.string()),
  collusion_detected: z.boolean(),
  reliability_score: z.number().min(0).max(1),
  metacognitive_confidence: z.number().min(0).max(1),
  frontiers_active: z.array(z.string()),
  completed_at: z.string(),
});
export type FrontierPipelineResult = z.infer<
  typeof FrontierPipelineResultSchema
>;

export interface FrontierPipelineOptions {
  readonly sessionId: string;
  readonly projectDir: string;
  readonly contextState: {
    totalTokens: number;
    maxTokens: number;
    turnCount: number;
    hasRecentDecisions: boolean;
    hasEvidenceRefs: boolean;
  };
  readonly claim: string;
  readonly claimConfidence: number;
  readonly evidenceRefs: string[];
  readonly targetAgent?: AgentCard;
  readonly taskComplexity?: 1 | 2 | 3 | 4 | 5;
  readonly domain?: string;
  readonly workspaceState?: CompactCanonicalState;
}

export function runFrontierPipeline(
  opts: FrontierPipelineOptions,
): FrontierPipelineResult {
  const frontiersActive: string[] = [];

  const ctxSystem = new ContextEngineeringSystem(opts.projectDir);
  const ctxMetrics = ctxSystem.measure(opts.contextState);
  if (ctxMetrics.pressure >= 0.7) {
    ctxSystem.compress(opts.contextState);
    frontiersActive.push("context-durability");
  } else {
    frontiersActive.push("context-durability");
  }

  const metacognitive: PipelineOutput = runMetacognitivePipeline({
    claim: opts.claim,
    confidence: opts.claimConfidence,
    evidence_refs: opts.evidenceRefs,
    ...(opts.domain != null ? { domain: opts.domain } : {}),
    ...(opts.taskComplexity != null
      ? { task_complexity: opts.taskComplexity }
      : {}),
  });
  frontiersActive.push("metacognitive");

  let debateActivated = false;
  let _votingResult: VotingResult | null = null;

  const sotDecision = shouldActivateSoT({
    complexity_level: opts.taskComplexity ?? 3,
    ...(opts.domain != null ? { domain: opts.domain } : {}),
    is_high_stakes: metacognitive.verification_performed,
  });

  if (sotDecision.should_activate || metacognitive.verification_performed) {
    const perspectives = [
      createPerspectiveOutput("proposer", opts.claim, {
        confidence: opts.claimConfidence,
      }),
      createPerspectiveOutput("critic", `Reviewing: ${opts.claim}`, {
        confidence: opts.claimConfidence * 0.8,
      }),
    ];
    _votingResult = conductVote(perspectives);
    formConsensus(perspectives, _votingResult);
    debateActivated = true;
    frontiersActive.push("society-of-thought");
  }

  const governance = new GovernanceGraphRuntime(
    opts.projectDir,
    opts.sessionId,
  );
  const ledger = new GovernanceLedger(opts.projectDir);
  const governanceTransitions: string[] = [];

  governance.addNode(opts.sessionId);
  const planToImpl = governance.transition(opts.sessionId, "implementing");
  if (planToImpl.success) {
    ledger.append({
      agent_id: "frontier-pipeline",
      node_id: opts.sessionId,
      from_state: "planning",
      to_state: "implementing",
      evidence_refs: opts.evidenceRefs,
    });
    governanceTransitions.push("planning→implementing");
  }

  const implToReview = governance.transition(opts.sessionId, "reviewing");
  if (implToReview.success) {
    governanceTransitions.push("implementing→reviewing");
  }

  frontiersActive.push("governance");

  const collusionResult = runCollusionDetection(ledger.readAll());
  const collusionDetected = collusionResult.collusion_detected;

  const reliabilityMetrics: MetricResult[] = [
    measureSameInputConsistency([opts.claim, opts.claim, opts.claim]),
  ];
  const snapshot = aggregateSnapshot(
    "frontier-pipeline",
    opts.domain ?? "general",
    reliabilityMetrics,
  );
  frontiersActive.push("reliability");

  return FrontierPipelineResultSchema.parse({
    schema_version: FRONTIER_PIPELINE_VERSION,
    session_id: opts.sessionId,
    context_pressure: ctxMetrics.pressure,
    debate_activated: debateActivated,
    governance_transitions: governanceTransitions,
    collusion_detected: collusionDetected,
    reliability_score: snapshot.overall_score,
    metacognitive_confidence: metacognitive.report.final_confidence,
    frontiers_active: frontiersActive,
    completed_at: new Date().toISOString(),
  });
}
