import { describe, test, expect } from "bun:test";
import {
  MAX_TOKEN_COST_MULTIPLIER,
  VotingResultSchema,
  castVoteFromPerspective,
  tallyVotes,
  determineVotingMode,
  conductVote,
} from "./voting.js";
import { createPerspectiveOutput } from "./perspectives.js";

describe("debate/voting", () => {
  test("MAX_TOKEN_COST_MULTIPLIER is 3", () => {
    expect(MAX_TOKEN_COST_MULTIPLIER).toBe(3.0);
  });

  describe("castVoteFromPerspective", () => {
    test("confident proposer votes accept", () => {
      const output = createPerspectiveOutput("proposer", "Use JWT", {
        confidence: 0.9,
      });
      const vote = castVoteFromPerspective(output);
      expect(vote.verdict).toBe("accept");
    });

    test("proposer with blocking concern votes reject", () => {
      const output = createPerspectiveOutput("proposer", "Use JWT", {
        confidence: 0.9,
        disagreements: [
          {
            role: "proposer",
            claim: "Safe",
            rationale: "Not safe",
            severity: "blocking",
            evidence: [],
          },
        ],
      });
      const vote = castVoteFromPerspective(output);
      expect(vote.verdict).toBe("reject");
    });

    test("reconciler always abstains", () => {
      const output = createPerspectiveOutput("reconciler", "Synthesizing", {
        confidence: 0.9,
      });
      const vote = castVoteFromPerspective(output);
      expect(vote.verdict).toBe("abstain");
    });
  });

  describe("tallyVotes", () => {
    test("counts accept, reject, abstain correctly", () => {
      const votes = [
        {
          perspective_role: "proposer",
          verdict: "accept" as const,
          confidence: 0.9,
          rationale: "",
          token_cost: 100,
        },
        {
          perspective_role: "critic",
          verdict: "accept" as const,
          confidence: 0.8,
          rationale: "",
          token_cost: 100,
        },
        {
          perspective_role: "red-team",
          verdict: "reject" as const,
          confidence: 0.7,
          rationale: "",
          token_cost: 100,
        },
      ];
      const tally = tallyVotes(votes);
      expect(tally.accept).toBe(2);
      expect(tally.reject).toBe(1);
      expect(tally.abstain).toBe(0);
    });
  });

  describe("determineVotingMode", () => {
    test("all accept → unanimous", () => {
      expect(determineVotingMode({ accept: 3, reject: 0, abstain: 0 })).toBe(
        "unanimous",
      );
    });

    test("majority accept → majority", () => {
      expect(determineVotingMode({ accept: 2, reject: 1, abstain: 0 })).toBe(
        "majority",
      );
    });

    test("tie → split", () => {
      expect(determineVotingMode({ accept: 1, reject: 1, abstain: 0 })).toBe(
        "split",
      );
    });

    test("no accept and no reject → unanimous", () => {
      expect(determineVotingMode({ accept: 0, reject: 0, abstain: 3 })).toBe(
        "unanimous",
      );
    });
  });

  describe("conductVote", () => {
    test("unanimous accept → final_verdict accept", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Use JWT", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "JWT is fine", { confidence: 0.85 }),
      ];
      const result = conductVote(perspectives);
      expect(result.final_verdict).toBe("accept");
    });

    test("split vote → escalate", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Use JWT", { confidence: 0.9 }),
        createPerspectiveOutput("red-team", "Security risk", {
          confidence: 0.3,
          disagreements: [
            {
              role: "proposer",
              claim: "Safe",
              rationale: "Not safe",
              severity: "blocking",
              evidence: [],
            },
          ],
        }),
      ];
      const result = conductVote(perspectives);
      expect(result.final_verdict).toBe("escalate");
    });

    test("token cost multiplier tracked", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Position", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "Position", { confidence: 0.8 }),
        createPerspectiveOutput("red-team", "Position", { confidence: 0.7 }),
      ];
      const result = conductVote(perspectives, 100, 100);
      expect(result.token_cost_multiplier).toBeGreaterThan(0);
      expect(result.total_token_cost).toBe(300);
    });

    test("dissent is recorded when any vote rejects", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Position", { confidence: 0.9 }),
        createPerspectiveOutput("red-team", "Position", {
          confidence: 0.2,
          disagreements: [
            {
              role: "proposer",
              claim: "Safe",
              rationale: "Not safe",
              severity: "major",
              evidence: [],
            },
          ],
        }),
      ];
      const result = conductVote(perspectives);
      expect(result.dissent_recorded).toBe(true);
    });

    test("result validates against schema", () => {
      const perspectives = [
        createPerspectiveOutput("proposer", "Test", { confidence: 0.9 }),
      ];
      const result = conductVote(perspectives);
      expect(VotingResultSchema.safeParse(result).success).toBe(true);
    });
  });
});
