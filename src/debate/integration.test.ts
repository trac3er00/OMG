import { describe, test, expect } from "bun:test";
import {
  runPlanningDebate,
  isBlockingIssue,
  formatDebateSummary,
  toTaskComplexityLevel,
  DEFAULT_DEBATE_CONFIG,
  type PlanningDecision,
  type DebateOutcome,
  type DebateIntegrationConfig,
} from "./integration.js";
import { SOT_COMPLEXITY_THRESHOLD } from "./perspectives.js";

describe("debate/integration", () => {
  describe("toTaskComplexityLevel", () => {
    test("maps 1-10 range to 1-5", () => {
      expect(toTaskComplexityLevel(1)).toBe(1);
      expect(toTaskComplexityLevel(2)).toBe(1);
      expect(toTaskComplexityLevel(3)).toBe(2);
      expect(toTaskComplexityLevel(4)).toBe(2);
      expect(toTaskComplexityLevel(5)).toBe(3);
      expect(toTaskComplexityLevel(6)).toBe(3);
      expect(toTaskComplexityLevel(7)).toBe(4);
      expect(toTaskComplexityLevel(8)).toBe(4);
      expect(toTaskComplexityLevel(9)).toBe(5);
      expect(toTaskComplexityLevel(10)).toBe(5);
    });

    test("clamps below 1", () => {
      expect(toTaskComplexityLevel(0)).toBe(1);
      expect(toTaskComplexityLevel(-5)).toBe(1);
    });

    test("clamps above 5", () => {
      expect(toTaskComplexityLevel(20)).toBe(5);
    });
  });

  describe("DEFAULT_DEBATE_CONFIG", () => {
    test("uses SOT_COMPLEXITY_THRESHOLD", () => {
      expect(DEFAULT_DEBATE_CONFIG.complexityThreshold).toBe(
        SOT_COMPLEXITY_THRESHOLD,
      );
    });

    test("enabled by default", () => {
      expect(DEFAULT_DEBATE_CONFIG.enabled).toBe(true);
    });

    test("max 3 debates per plan", () => {
      expect(DEFAULT_DEBATE_CONFIG.maxDebatesPerPlan).toBe(3);
    });
  });

  describe("runPlanningDebate — planning-pipeline", () => {
    test("high-complexity decision triggers debate with 5 perspectives across 3 rounds", async () => {
      const decision: PlanningDecision = {
        topic: "Database migration strategy",
        complexity: 8,
        context: "Production PostgreSQL to CockroachDB migration",
        alternatives: ["blue-green deployment", "rolling migration"],
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.invoked).toBe(true);
      expect(outcome.skipped).toBe(false);
      expect(outcome.error).toBeUndefined();
      expect(outcome.transcript).toBeDefined();
      expect(outcome.transcript!.rounds).toHaveLength(3);

      const round1 = outcome.transcript!.rounds[0]!;
      const perspectiveKeys = Object.keys(round1.perspectives);
      expect(perspectiveKeys).toContain("proposer");
      expect(perspectiveKeys).toContain("critic");
      expect(perspectiveKeys).toContain("red-team");
      expect(perspectiveKeys).toContain("domain-expert");
      expect(perspectiveKeys).toContain("reconciler");
      expect(perspectiveKeys).toHaveLength(5);
    });

    test("consensus is reached (not failed) for standard debate", async () => {
      const decision: PlanningDecision = {
        topic: "API versioning strategy",
        complexity: 7,
        context: "REST API v2 migration",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.invoked).toBe(true);
      expect(outcome.transcript).toBeDefined();
      const status = outcome.transcript!.consensus.status;
      expect(["accepted", "dissent", "forced"]).toContain(status);
    });

    test("debate transcript includes voting result", async () => {
      const decision: PlanningDecision = {
        topic: "Auth system redesign",
        complexity: 9,
        context: "Moving from session to JWT",
        domain: "authentication",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.transcript).toBeDefined();
      const vr = outcome.transcript!.votingResult;
      expect(["accept", "reject", "escalate"]).toContain(vr.verdict);
      expect(vr.acceptCount + vr.rejectCount + vr.abstainCount).toBeGreaterThan(
        0,
      );
      expect(vr.aggregateConfidence).toBeGreaterThanOrEqual(0);
      expect(vr.aggregateConfidence).toBeLessThanOrEqual(1);
    });

    test("plan summary is attached to outcome", async () => {
      const decision: PlanningDecision = {
        topic: "Caching layer",
        complexity: 6,
        context: "Redis integration",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.planSummary).toBeDefined();
      expect(outcome.planSummary!).toContain("Caching layer");
      expect(outcome.planSummary!).toContain("Debate on");
    });
  });

  describe("runPlanningDebate — skip-simple", () => {
    test("low-complexity decision skips debate", async () => {
      const decision: PlanningDecision = {
        topic: "Update README typo",
        complexity: 1,
        context: "Fix typo in documentation",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.invoked).toBe(false);
      expect(outcome.skipped).toBe(true);
      expect(outcome.skipReason).toBeDefined();
      expect(outcome.skipReason!).toContain("below threshold");
      expect(outcome.transcript).toBeUndefined();
    });

    test("disabled config skips debate", async () => {
      const config: DebateIntegrationConfig = {
        enabled: false,
        complexityThreshold: SOT_COMPLEXITY_THRESHOLD,
        maxDebatesPerPlan: 3,
      };

      const decision: PlanningDecision = {
        topic: "Major refactor",
        complexity: 10,
        context: "Full rewrite",
      };

      const outcome = await runPlanningDebate(decision, config);

      expect(outcome.invoked).toBe(false);
      expect(outcome.skipped).toBe(true);
      expect(outcome.skipReason).toBe("debate disabled");
    });

    test("complexity at threshold boundary triggers debate", async () => {
      const decision: PlanningDecision = {
        topic: "Moderate change",
        complexity: SOT_COMPLEXITY_THRESHOLD * 2,
        context: "At threshold boundary",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.invoked).toBe(true);
      expect(outcome.skipped).toBe(false);
    });

    test("critical domain activates even at low complexity", async () => {
      const decision: PlanningDecision = {
        topic: "Security patch",
        complexity: 2,
        context: "Fix auth bypass",
        domain: "security",
      };

      const outcome = await runPlanningDebate(decision);

      expect(outcome.invoked).toBe(true);
      expect(outcome.skipped).toBe(false);
    });
  });

  describe("isBlockingIssue", () => {
    test("returns false for skipped outcome", () => {
      const outcome: DebateOutcome = {
        invoked: false,
        skipped: true,
        skipReason: "test",
      };
      expect(isBlockingIssue(outcome)).toBe(false);
    });

    test("returns false when consensus is accepted", () => {
      const outcome: DebateOutcome = {
        invoked: true,
        skipped: false,
        transcript: {
          rounds: [],
          consensus: {
            status: "accepted",
            resolution: "all agreed",
            dissenting: [],
            blockingIssues: [],
            governanceEscalationRequired: false,
          },
          votingResult: {
            verdict: "accept",
            votingMode: "unanimous",
            acceptCount: 4,
            rejectCount: 0,
            abstainCount: 1,
            aggregateConfidence: 0.8,
          },
        },
      };
      expect(isBlockingIssue(outcome)).toBe(false);
    });

    test("returns true when escalated with governance escalation", () => {
      const outcome: DebateOutcome = {
        invoked: true,
        skipped: false,
        transcript: {
          rounds: [],
          consensus: {
            status: "escalated",
            resolution: "cannot proceed",
            dissenting: ["critical flaw found"],
            blockingIssues: ["security vulnerability in auth flow"],
            governanceEscalationRequired: true,
          },
          votingResult: {
            verdict: "reject",
            votingMode: "majority",
            acceptCount: 1,
            rejectCount: 3,
            abstainCount: 1,
            aggregateConfidence: 0.4,
          },
        },
      };
      expect(isBlockingIssue(outcome)).toBe(true);
    });

    test("returns false when escalated without governance requirement", () => {
      const outcome: DebateOutcome = {
        invoked: true,
        skipped: false,
        transcript: {
          rounds: [],
          consensus: {
            status: "escalated",
            resolution: "needs review",
            dissenting: [],
            blockingIssues: [],
            governanceEscalationRequired: false,
          },
          votingResult: {
            verdict: "escalate",
            votingMode: "split",
            acceptCount: 2,
            rejectCount: 2,
            abstainCount: 1,
            aggregateConfidence: 0.5,
          },
        },
      };
      expect(isBlockingIssue(outcome)).toBe(false);
    });
  });

  describe("formatDebateSummary", () => {
    test("returns empty string when no debates invoked", () => {
      const outcomes: DebateOutcome[] = [
        { invoked: false, skipped: true, skipReason: "too simple" },
      ];
      expect(formatDebateSummary(outcomes)).toBe("");
    });

    test("produces valid markdown with heading", () => {
      const outcomes: DebateOutcome[] = [
        {
          invoked: true,
          skipped: false,
          planSummary: 'Debate on "Auth": accepted. Decision: Use JWT',
          transcript: {
            rounds: [],
            consensus: {
              status: "accepted",
              resolution: "Use JWT",
              dissenting: [],
              blockingIssues: [],
              governanceEscalationRequired: false,
            },
            votingResult: {
              verdict: "accept",
              votingMode: "unanimous",
              acceptCount: 4,
              rejectCount: 0,
              abstainCount: 1,
              aggregateConfidence: 0.8,
            },
          },
        },
      ];

      const md = formatDebateSummary(outcomes);

      expect(md).toContain("## Debate Summary");
      expect(md).toContain("Auth");
      expect(md).toContain("Consensus: accepted");
      expect(md).toContain("Vote: accept (4/0/1)");
    });

    test("includes blocking issues in markdown", () => {
      const outcomes: DebateOutcome[] = [
        {
          invoked: true,
          skipped: false,
          planSummary: 'Debate on "Deploy": escalated',
          transcript: {
            rounds: [],
            consensus: {
              status: "escalated",
              resolution: "halted",
              dissenting: ["risk too high"],
              blockingIssues: ["No rollback plan"],
              governanceEscalationRequired: true,
            },
            votingResult: {
              verdict: "reject",
              votingMode: "majority",
              acceptCount: 1,
              rejectCount: 3,
              abstainCount: 1,
              aggregateConfidence: 0.3,
            },
          },
        },
      ];

      const md = formatDebateSummary(outcomes);

      expect(md).toContain("**Blocking issues**");
      expect(md).toContain("No rollback plan");
    });

    test("excludes errored outcomes", () => {
      const outcomes: DebateOutcome[] = [
        {
          invoked: true,
          skipped: false,
          error: "LLM timeout",
        },
      ];
      expect(formatDebateSummary(outcomes)).toBe("");
    });

    test("handles multiple debate outcomes", () => {
      const outcomes: DebateOutcome[] = [
        {
          invoked: true,
          skipped: false,
          planSummary: "Debate A",
          transcript: {
            rounds: [],
            consensus: {
              status: "accepted",
              resolution: "ok",
              dissenting: [],
              blockingIssues: [],
              governanceEscalationRequired: false,
            },
            votingResult: {
              verdict: "accept",
              votingMode: "unanimous",
              acceptCount: 4,
              rejectCount: 0,
              abstainCount: 1,
              aggregateConfidence: 0.9,
            },
          },
        },
        { invoked: false, skipped: true, skipReason: "simple" },
        {
          invoked: true,
          skipped: false,
          planSummary: "Debate B",
          transcript: {
            rounds: [],
            consensus: {
              status: "dissent",
              resolution: "minor issues",
              dissenting: ["naming"],
              blockingIssues: [],
              governanceEscalationRequired: false,
            },
            votingResult: {
              verdict: "accept",
              votingMode: "majority",
              acceptCount: 3,
              rejectCount: 1,
              abstainCount: 1,
              aggregateConfidence: 0.7,
            },
          },
        },
      ];

      const md = formatDebateSummary(outcomes);

      expect(md).toContain("Debate A");
      expect(md).toContain("Debate B");
      const bulletCount = (md.match(/^- /gm) || []).length;
      expect(bulletCount).toBe(2);
    });
  });
});
