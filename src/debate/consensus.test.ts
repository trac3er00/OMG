import { describe, test, expect } from "bun:test";
import { formConsensus, ConsensusReportSchema } from "./consensus.js";
import { createPerspectiveOutput } from "./perspectives.js";
import { conductVote } from "./voting.js";

describe("debate/consensus", () => {
  describe("formConsensus", () => {
    test("unanimous agreement → accepted status", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Use JWT", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "JWT is fine", { confidence: 0.85 }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult);
      expect(report.status).toBe("accepted");
    });

    test("blocking disagreement → escalated with governance_escalation_required", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Use JWT", { confidence: 0.9 }),
        createPerspectiveOutput("red-team", "Security flaw", {
          confidence: 0.3,
          disagreements: [
            {
              role: "proposer",
              claim: "JWT is safe",
              rationale: "Vulnerable",
              severity: "blocking",
              evidence: [],
            },
          ],
        }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult);
      expect(report.status).toBe("escalated");
      expect(report.governance_escalation_required).toBe(true);
      expect(report.blocking_issues.length).toBeGreaterThan(0);
    });

    test("split vote → escalated (without governance requirement)", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Position A", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "Position B", {
          confidence: 0.2,
          disagreements: [
            {
              role: "proposer",
              claim: "A is right",
              rationale: "B is better",
              severity: "major",
              evidence: [],
            },
          ],
        }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult);
      expect(["escalated", "rejected"]).toContain(report.status);
    });

    test("max rounds reached without consensus → forced status", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Position", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "Counter", {
          confidence: 0.2,
          disagreements: [
            {
              role: "proposer",
              claim: "Claim",
              rationale: "Against",
              severity: "major",
              evidence: [],
            },
          ],
        }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult, 3);
      expect(["forced", "escalated", "rejected"]).toContain(report.status);
    });

    test("all dissent is always recorded", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Position A", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "Issues", {
          confidence: 0.5,
          disagreements: [
            {
              role: "proposer",
              claim: "Claim X",
              rationale: "Issue Y",
              severity: "minor",
              evidence: [],
            },
          ],
        }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult);
      expect(report.all_dissent_recorded).toBe(true);
    });

    test("report validates against schema", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Test", { confidence: 0.9 }),
      ];
      const votingResult = conductVote(perspectives);
      const report = formConsensus(perspectives, votingResult);
      expect(ConsensusReportSchema.safeParse(report).success).toBe(true);
    });
  });
});
