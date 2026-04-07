import {
  type PerspectiveRole,
  type PerspectiveOutput,
  type TaskComplexityLevel,
  SOT_COMPLEXITY_THRESHOLD,
  MAX_DEBATE_ROUNDS,
  PERSPECTIVE_PROMPTS,
  shouldActivateSoT,
  createPerspectiveOutput,
} from "./perspectives.js";
import { type ConsensusReport, formConsensus } from "./consensus.js";
import { type VotingResult, conductVote } from "./voting.js";

export interface PlanningDecision {
  readonly topic: string;
  readonly complexity: number;
  readonly context: string;
  readonly domain?: string;
  readonly is_high_stakes?: boolean;
  readonly alternatives?: readonly string[];
}

export interface DebateRound {
  readonly round: number;
  readonly perspectives: Record<string, string>;
}

export interface DebateTranscript {
  readonly rounds: readonly DebateRound[];
  readonly consensus: {
    readonly status: ConsensusReport["status"];
    readonly resolution: string;
    readonly dissenting: readonly string[];
    readonly blockingIssues: readonly string[];
    readonly governanceEscalationRequired: boolean;
  };
  readonly votingResult: {
    readonly verdict: VotingResult["final_verdict"];
    readonly votingMode: VotingResult["voting_mode"];
    readonly acceptCount: number;
    readonly rejectCount: number;
    readonly abstainCount: number;
    readonly aggregateConfidence: number;
  };
}

export interface DebateOutcome {
  readonly invoked: boolean;
  readonly skipped: boolean;
  readonly skipReason?: string;
  readonly transcript?: DebateTranscript;
  readonly planSummary?: string;
  readonly error?: string;
}

export interface DebateIntegrationConfig {
  readonly enabled: boolean;
  readonly complexityThreshold: number;
  readonly maxDebatesPerPlan: number;
}

export { SOT_COMPLEXITY_THRESHOLD };

export const DEFAULT_DEBATE_CONFIG: DebateIntegrationConfig = {
  enabled: true,
  complexityThreshold: SOT_COMPLEXITY_THRESHOLD,
  maxDebatesPerPlan: 3,
};

const ALL_ROLES: readonly PerspectiveRole[] = [
  "proposer",
  "critic",
  "red-team",
  "domain-expert",
  "reconciler",
] as const;

/** Map 1–10 planning complexity → 1–5 TaskComplexityLevel, clamped. */
export function toTaskComplexityLevel(c: number): TaskComplexityLevel {
  const clamped = Math.max(1, Math.min(5, Math.ceil(c / 2)));
  return clamped as TaskComplexityLevel;
}

function generateRolePosition(
  role: PerspectiveRole,
  topic: string,
  context: string,
  alternatives: readonly string[],
): string {
  const altClause =
    alternatives.length > 0
      ? ` Alternatives considered: ${alternatives.join(", ")}.`
      : "";
  return `[${role}] Analysis of "${topic}": ${PERSPECTIVE_PROMPTS[role]}${altClause} Context: ${context}`;
}

export async function runPlanningDebate(
  decision: PlanningDecision,
  config: DebateIntegrationConfig = DEFAULT_DEBATE_CONFIG,
): Promise<DebateOutcome> {
  if (!config.enabled) {
    return { invoked: false, skipped: true, skipReason: "debate disabled" };
  }

  const complexityLevel = toTaskComplexityLevel(decision.complexity);
  const activationOpts: {
    complexity_level: TaskComplexityLevel;
    domain?: string;
    is_high_stakes?: boolean;
  } = { complexity_level: complexityLevel };
  if (decision.domain != null) activationOpts.domain = decision.domain;
  if (decision.is_high_stakes != null)
    activationOpts.is_high_stakes = decision.is_high_stakes;

  const activation = shouldActivateSoT(activationOpts);

  if (!activation.should_activate) {
    return {
      invoked: false,
      skipped: true,
      skipReason: `complexity ${decision.complexity} (level ${complexityLevel}) below threshold: ${activation.reason}`,
    };
  }

  try {
    const alternatives = decision.alternatives ?? [];
    const rounds: DebateRound[] = [];
    let allPerspectives: PerspectiveOutput[] = [];

    for (let round = 1; round <= MAX_DEBATE_ROUNDS; round++) {
      const roundPerspectives: Record<string, string> = {};
      const roundOutputs: PerspectiveOutput[] = [];

      for (const role of ALL_ROLES) {
        const position = generateRolePosition(
          role,
          decision.topic,
          decision.context,
          alternatives,
        );

        const disagreements =
          round > 1 && (role === "critic" || role === "red-team")
            ? [
                {
                  role: "proposer" as const,
                  claim: `Round ${round} challenge on: ${decision.topic}`,
                  rationale: `${role} challenges proposal in round ${round}`,
                  severity: "minor" as const,
                  evidence: [] as string[],
                },
              ]
            : [];

        const output = createPerspectiveOutput(role, position, {
          round,
          confidence: role === "reconciler" ? 0.8 : 0.7,
          disagreements,
        });

        roundPerspectives[role] = position;
        roundOutputs.push(output);
      }

      rounds.push({ round, perspectives: roundPerspectives });
      allPerspectives = [...allPerspectives, ...roundOutputs];
    }

    const finalRoundPerspectives = allPerspectives.filter(
      (p) => p.round === MAX_DEBATE_ROUNDS,
    );

    const votingResult = conductVote(finalRoundPerspectives);
    const consensusReport = formConsensus(
      finalRoundPerspectives,
      votingResult,
      MAX_DEBATE_ROUNDS,
    );

    const transcript: DebateTranscript = {
      rounds,
      consensus: {
        status: consensusReport.status,
        resolution: consensusReport.final_position,
        dissenting: consensusReport.dissent_areas,
        blockingIssues: consensusReport.blocking_issues,
        governanceEscalationRequired:
          consensusReport.governance_escalation_required,
      },
      votingResult: {
        verdict: votingResult.final_verdict,
        votingMode: votingResult.voting_mode,
        acceptCount: votingResult.accept_count,
        rejectCount: votingResult.reject_count,
        abstainCount: votingResult.abstain_count,
        aggregateConfidence: votingResult.aggregate_confidence,
      },
    };

    const statusLabel =
      consensusReport.status === "escalated" &&
      consensusReport.governance_escalation_required
        ? "BLOCKING — governance escalation required"
        : consensusReport.status;

    const planSummary = `Debate on "${decision.topic}": ${statusLabel}. Decision: ${consensusReport.final_position.slice(0, 120)}`;

    return {
      invoked: true,
      skipped: false,
      transcript,
      planSummary,
    };
  } catch (error) {
    return {
      invoked: true,
      skipped: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

export function isBlockingIssue(outcome: DebateOutcome): boolean {
  if (!outcome.transcript) return false;
  return (
    outcome.transcript.consensus.status === "escalated" &&
    outcome.transcript.consensus.governanceEscalationRequired
  );
}

export function formatDebateSummary(
  outcomes: readonly DebateOutcome[],
): string {
  const invoked = outcomes.filter((o) => o.invoked && !o.error);
  if (invoked.length === 0) return "";

  const lines: string[] = ["## Debate Summary", ""];
  for (const outcome of invoked) {
    if (outcome.planSummary) {
      lines.push(`- ${outcome.planSummary}`);
    }
    if (outcome.transcript) {
      const { consensus, votingResult } = outcome.transcript;
      lines.push(
        `  - Consensus: ${consensus.status} | Vote: ${votingResult.verdict} (${votingResult.acceptCount}/${votingResult.rejectCount}/${votingResult.abstainCount})`,
      );
      if (consensus.blockingIssues.length > 0) {
        lines.push(
          `  - **Blocking issues**: ${consensus.blockingIssues.join("; ")}`,
        );
      }
    }
  }

  return lines.join("\n");
}
