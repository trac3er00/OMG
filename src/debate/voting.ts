import { z } from "zod";
import { type PerspectiveOutput } from "./perspectives.js";

export const MAX_TOKEN_COST_MULTIPLIER = 3.0;
export const MIN_PERSPECTIVES_FOR_VOTE = 2;
export const MAX_VOTING_ROUNDS = 3;

export type VotingMode = "unanimous" | "majority" | "split";
export type VotingVerdict = "accept" | "reject" | "escalate";

export const VoteSchema = z.object({
  perspective_role: z.string(),
  verdict: z.enum(["accept", "reject", "abstain"]),
  confidence: z.number().min(0).max(1),
  rationale: z.string(),
  token_cost: z.number().min(0),
});
export type Vote = z.infer<typeof VoteSchema>;

export const VotingResultSchema = z.object({
  voting_mode: z.enum(["unanimous", "majority", "split"]),
  final_verdict: z.enum(["accept", "reject", "escalate"]),
  votes: z.array(VoteSchema),
  accept_count: z.number().int(),
  reject_count: z.number().int(),
  abstain_count: z.number().int(),
  aggregate_confidence: z.number().min(0).max(1),
  total_token_cost: z.number().min(0),
  token_cost_multiplier: z.number().min(0),
  rounds_used: z.number().int().min(1),
  dissent_recorded: z.boolean(),
});
export type VotingResult = z.infer<typeof VotingResultSchema>;

export function castVoteFromPerspective(
  output: PerspectiveOutput,
  baseTokenCost = 100,
): Vote {
  const hasBlockingConcerns = output.disagreements.some(
    (d) => d.severity === "blocking",
  );
  const hasMajorConcerns = output.disagreements.some(
    (d) => d.severity === "major",
  );

  const verdict =
    output.role === "reconciler"
      ? "abstain"
      : hasBlockingConcerns
        ? "reject"
        : output.confidence >= 0.6
          ? "accept"
          : hasMajorConcerns
            ? "reject"
            : "abstain";

  return VoteSchema.parse({
    perspective_role: output.role,
    verdict,
    confidence: output.confidence,
    rationale: output.rationale,
    token_cost: baseTokenCost,
  });
}

export function tallyVotes(votes: readonly Vote[]): {
  accept: number;
  reject: number;
  abstain: number;
} {
  return votes.reduce(
    (acc, v) => {
      if (v.verdict === "accept") acc.accept++;
      else if (v.verdict === "reject") acc.reject++;
      else acc.abstain++;
      return acc;
    },
    { accept: 0, reject: 0, abstain: 0 },
  );
}

export function determineVotingMode(tally: {
  accept: number;
  reject: number;
  abstain: number;
}): VotingMode {
  const total = tally.accept + tally.reject;
  if (total === 0) return "unanimous";
  if (tally.reject === 0) return "unanimous";
  if (tally.accept > tally.reject) return "majority";
  if (tally.reject > tally.accept) return "majority";
  return "split";
}

export function conductVote(
  perspectives: readonly PerspectiveOutput[],
  baseTokenCostPerPerspective = 100,
  singleAgentBaselineCost = 100,
): VotingResult {
  const actionablePerspectives = perspectives.filter(
    (p) => p.role !== "reconciler",
  );
  const votes = actionablePerspectives.map((p) =>
    castVoteFromPerspective(p, baseTokenCostPerPerspective),
  );
  const tally = tallyVotes(votes);
  const votingMode = determineVotingMode(tally);

  const finalVerdict: VotingVerdict =
    votingMode === "unanimous" && tally.reject === 0
      ? "accept"
      : votingMode === "split"
        ? "escalate"
        : tally.accept > tally.reject
          ? "accept"
          : "reject";

  const totalTokenCost = votes.reduce((sum, v) => sum + v.token_cost, 0);
  const tokenCostMultiplier =
    singleAgentBaselineCost > 0 ? totalTokenCost / singleAgentBaselineCost : 1;
  const aggregate_confidence =
    votes.length === 0
      ? 0
      : votes.reduce((sum, v) => sum + v.confidence, 0) / votes.length;

  const dissent_recorded =
    votes.some((v) => v.verdict === "reject") ||
    perspectives.some((p) => p.disagreements.length > 0);

  return VotingResultSchema.parse({
    voting_mode: votingMode,
    final_verdict: finalVerdict,
    votes,
    accept_count: tally.accept,
    reject_count: tally.reject,
    abstain_count: tally.abstain,
    aggregate_confidence,
    total_token_cost: totalTokenCost,
    token_cost_multiplier: tokenCostMultiplier,
    rounds_used: 1,
    dissent_recorded,
  });
}
