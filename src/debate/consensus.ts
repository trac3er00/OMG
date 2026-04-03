import { z } from "zod";
import { type PerspectiveOutput, MAX_DEBATE_ROUNDS } from "./perspectives.js";
import { type VotingResult } from "./voting.js";

export type ConsensusStatus =
  | "accepted"
  | "rejected"
  | "dissent"
  | "escalated"
  | "forced";

export const ConsensusReportSchema = z.object({
  status: z.enum(["accepted", "rejected", "dissent", "escalated", "forced"]),
  agreement_areas: z.array(z.string()),
  dissent_areas: z.array(z.string()),
  blocking_issues: z.array(z.string()),
  rounds_used: z.number().int().min(1),
  final_position: z.string(),
  all_dissent_recorded: z.boolean(),
  governance_escalation_required: z.boolean(),
});
export type ConsensusReport = z.infer<typeof ConsensusReportSchema>;

export function formConsensus(
  perspectives: readonly PerspectiveOutput[],
  votingResult: VotingResult,
  rounds = 1,
): ConsensusReport {
  const allDisagreements = perspectives.flatMap((p) => p.disagreements);
  const blockingIssues = allDisagreements
    .filter((d) => d.severity === "blocking")
    .map((d) => d.claim);
  const majorIssues = allDisagreements
    .filter((d) => d.severity === "major")
    .map((d) => d.claim);
  const minorIssues = allDisagreements.filter((d) => d.severity === "minor");

  const proposer = perspectives.find((p) => p.role === "proposer");
  const finalPosition =
    proposer?.position ??
    perspectives[0]?.position ??
    "No position established";

  const agreementAreas = perspectives
    .filter((p) => p.role !== "reconciler" && p.confidence >= 0.7)
    .map((p) => `${p.role}: ${p.position.slice(0, 50)}`);

  const dissentAreas = [
    ...blockingIssues.map((i) => `[BLOCKING] ${i}`),
    ...majorIssues.map((i) => `[MAJOR] ${i}`),
    ...minorIssues.map((i) => i.claim),
  ];

  const allDissentRecorded = allDisagreements.every((d) =>
    dissentAreas.some((a) => a.includes(d.claim)),
  );

  if (blockingIssues.length > 0) {
    return ConsensusReportSchema.parse({
      status: "escalated",
      agreement_areas: agreementAreas,
      dissent_areas: dissentAreas,
      blocking_issues: blockingIssues,
      rounds_used: rounds,
      final_position: finalPosition,
      all_dissent_recorded: true,
      governance_escalation_required: true,
    });
  }

  if (votingResult.final_verdict === "escalate") {
    return ConsensusReportSchema.parse({
      status: "escalated",
      agreement_areas: agreementAreas,
      dissent_areas: dissentAreas,
      blocking_issues: [],
      rounds_used: rounds,
      final_position: finalPosition,
      all_dissent_recorded: allDissentRecorded,
      governance_escalation_required: false,
    });
  }

  if (rounds >= MAX_DEBATE_ROUNDS && votingResult.final_verdict !== "accept") {
    return ConsensusReportSchema.parse({
      status: "forced",
      agreement_areas: agreementAreas,
      dissent_areas: dissentAreas,
      blocking_issues: [],
      rounds_used: rounds,
      final_position: finalPosition,
      all_dissent_recorded: allDissentRecorded,
      governance_escalation_required: false,
    });
  }

  if (votingResult.final_verdict === "accept" && majorIssues.length === 0) {
    return ConsensusReportSchema.parse({
      status: minorIssues.length > 0 ? "dissent" : "accepted",
      agreement_areas: agreementAreas,
      dissent_areas: dissentAreas,
      blocking_issues: [],
      rounds_used: rounds,
      final_position: finalPosition,
      all_dissent_recorded: allDissentRecorded,
      governance_escalation_required: false,
    });
  }

  return ConsensusReportSchema.parse({
    status: votingResult.final_verdict === "accept" ? "dissent" : "rejected",
    agreement_areas: agreementAreas,
    dissent_areas: dissentAreas,
    blocking_issues: [],
    rounds_used: rounds,
    final_position: finalPosition,
    all_dissent_recorded: allDissentRecorded,
    governance_escalation_required: false,
  });
}
