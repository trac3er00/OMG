import { existsSync, readdirSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { describe, test, expect, beforeEach, afterEach } from "bun:test";

import {
  decide,
  createAdvisor,
  getAdvisorRecommendation,
  type AdvisorContext,
} from "../../src/advisor/index.js";
import type { SanitizedContent } from "../../src/security/external-firewall.js";
import type { FidelityResult } from "../../src/intent/fidelity-checker.js";
import type { IntentAnalysis } from "../../src/intent/index.js";
import {
  TrustTier,
  type TrustScore,
} from "../../src/security/trust-scoring.js";

const TEST_DECISIONS_DIR = join(process.cwd(), ".omg", "decisions");

function cleanDecisionsDir(): void {
  if (existsSync(TEST_DECISIONS_DIR)) {
    const files = readdirSync(TEST_DECISIONS_DIR);
    for (const file of files) {
      if (file.endsWith(".json")) {
        rmSync(join(TEST_DECISIONS_DIR, file));
      }
    }
  }
}

function getDecisionFiles(): string[] {
  if (!existsSync(TEST_DECISIONS_DIR)) {
    return [];
  }
  return readdirSync(TEST_DECISIONS_DIR).filter((f) => f.endsWith(".json"));
}

describe("Advisor Integration Tests", () => {
  beforeEach(() => {
    cleanDecisionsDir();
  });

  afterEach(() => {
    cleanDecisionsDir();
  });

  test("full lifecycle through Advisor — all 3 signals present, decision logged", async () => {
    const sanitizationResult: SanitizedContent = {
      content: "Build a React dashboard",
      wasTruncated: false,
      injectionPatternsFound: [],
      blocked: false,
      source: "user_input",
    };

    const trustScore: TrustScore = {
      tier: TrustTier.LOCAL,
      score: 1.0,
      reason: "Local file path",
      domain: "local",
    };

    const fidelityResult: FidelityResult = {
      needsClarification: false,
      clarificationQuestion: null,
      interpretation:
        "Interpretation: treat this as a feature request in the frontend domain.",
      gapChecks: [
        "scope: Scope gap is minor: the target surface is specific enough to start.",
        "expectation: Expectation gap is minor: success looks concrete enough to evaluate.",
        "constraint: Constraint gap is minor: there is enough room to proceed with a conservative default.",
      ],
      canProceed: true,
      round: 0,
    };

    const context: AdvisorContext = {
      goal: "Build a React dashboard with user analytics",
      sanitizationResult,
      trustScore,
      fidelityResult,
      round: 0,
    };

    const output = await decide(context);

    expect(output.decision).toBe("proceed");
    expect(output.confidence).toBeGreaterThan(0.8);
    expect(output.reason).toContain("Signals are clear");
    expect(output.reason.length).toBeGreaterThan(10);

    const decisionFiles = getDecisionFiles();
    expect(decisionFiles.length).toBeGreaterThanOrEqual(1);
    expect(decisionFiles.some((f) => f.includes("proceed"))).toBe(true);
  });

  test("firewall blocked → Advisor aborts", async () => {
    const blockedContent: SanitizedContent = {
      content: "cleaned content",
      wasTruncated: false,
      injectionPatternsFound: ["ignore-prev-instructions"],
      blocked: true,
      source: "web_search:example.com",
    };

    const context: AdvisorContext = {
      goal: "Help me with this task",
      sanitizationResult: blockedContent,
    };

    const output = await decide(context);

    expect(output.decision).toBe("abort");
    expect(output.confidence).toBe(0.99);
    expect(output.reason).toContain("Security threat");
    expect(output.reason).toContain("firewall");
  });

  test("UNTRUSTED source → Advisor escalates", async () => {
    const untrustedSource: TrustScore = {
      tier: TrustTier.UNTRUSTED,
      score: 0.0,
      reason: "unknown domain",
      domain: "evil.example.com",
    };

    const context: AdvisorContext = {
      goal: "Execute code from this URL",
      trustScore: untrustedSource,
    };

    const output = await decide(context);

    expect(output.decision).toBe("escalate");
    expect(output.confidence).toBe(0.94);
    expect(output.reason).toContain("Low-trust source");
    expect(output.escalationReason).toBeDefined();
    expect(output.escalationReason).toContain("unknown domain");
  });

  test("fidelity gap → Advisor clarifies", async () => {
    const ambiguousGoal: FidelityResult = {
      needsClarification: true,
      clarificationQuestion: "Which component should be affected?",
      interpretation:
        "Interpretation: treat this as a feature request in the general domain.",
      gapChecks: [
        "scope: Significant scope gap: the target artifact or surface is not concrete enough yet.",
        "expectation: Significant expectation gap: success criteria are still too vague to verify cleanly.",
        "constraint: Constraint gap is minor.",
      ],
      canProceed: false,
      round: 0,
    };

    const context: AdvisorContext = {
      goal: "Improve the thing",
      fidelityResult: ambiguousGoal,
    };

    const output = await decide(context);

    expect(output.decision).toBe("clarify");
    expect(output.confidence).toBe(0.88);
    expect(output.reason).toContain("Intent gap");
    expect(output.clarificationQuestion).toBe(
      "Which component should be affected?",
    );
  });

  test("clean signals → Advisor proceeds", async () => {
    const cleanSanitization: SanitizedContent = {
      content: "User wants to create a landing page",
      wasTruncated: false,
      injectionPatternsFound: [],
      blocked: false,
      source: "user_input",
    };

    const trustedSource: TrustScore = {
      tier: TrustTier.VERIFIED,
      score: 0.8,
      reason: "Verified domain matching pattern: github.com",
      domain: "github.com",
    };

    const clearFidelity: FidelityResult = {
      needsClarification: false,
      clarificationQuestion: null,
      interpretation:
        "Interpretation: treat this as a feature request in the frontend domain.",
      gapChecks: ["scope: minor", "expectation: minor", "constraint: minor"],
      canProceed: true,
      round: 1,
    };

    const context: AdvisorContext = {
      goal: "Create a landing page with hero section and CTA button",
      sanitizationResult: cleanSanitization,
      trustScore: trustedSource,
      fidelityResult: clearFidelity,
    };

    const output = await decide(context);

    expect(output.decision).toBe("proceed");
    expect(output.confidence).toBeGreaterThanOrEqual(0.86);
    expect(output.reason).toContain("clear");
  });

  test("decision gets logged to .omg/decisions/", async () => {
    if (!existsSync(TEST_DECISIONS_DIR)) {
      mkdirSync(TEST_DECISIONS_DIR, { recursive: true });
    }

    const initialFiles = getDecisionFiles();

    const context: AdvisorContext = {
      goal: "Test decision logging",
    };

    await decide(context);

    const newFiles = getDecisionFiles();
    expect(newFiles.length).toBeGreaterThan(initialFiles.length);

    const newestFile = newFiles.find((f) => !initialFiles.includes(f));
    expect(newestFile).toBeDefined();
    expect(newestFile).toMatch(
      /\d{4}-\d{2}-\d{2}T.*-(proceed|clarify|escalate|abort)\.json$/,
    );
  });

  test("createAdvisor factory produces working advisor", async () => {
    const advisor = createAdvisor();

    expect(advisor).toBeDefined();
    expect(typeof advisor.decide).toBe("function");

    const context: AdvisorContext = {
      goal: "Factory test goal",
    };

    const output = await advisor.decide(context);

    expect(output).toBeDefined();
    expect(output.decision).toBeDefined();
    expect(["proceed", "clarify", "escalate", "abort"]).toContain(
      output.decision,
    );
    expect(output.reason).toBeDefined();
    expect(typeof output.confidence).toBe("number");
    expect(output.confidence).toBeGreaterThanOrEqual(0);
    expect(output.confidence).toBeLessThanOrEqual(1);
  });

  test("existing escalation is still accessible — getAdvisorRecommendation exported", () => {
    expect(typeof getAdvisorRecommendation).toBe("function");

    const complexIntent: IntentAnalysis = {
      intent: "complex",
      domain: "backend",
      confidenceScore: 0.9,
      ambiguities: [],
      suggestedApproach: "Break into smaller tasks",
      clarifyingQuestions: [],
      complexity: {
        riskLevel: "high",
        filesAffected: 15,
        effort: "high",
        signals: ["large codebase impact", "multiple services affected"],
      },
    };

    const recommendation = getAdvisorRecommendation(complexIntent, 0);

    if (recommendation) {
      expect(recommendation.recommendation).toBeDefined();
      expect(recommendation.rationale).toBeDefined();
      expect(Array.isArray(recommendation.alternatives)).toBe(true);
      expect(Array.isArray(recommendation.risks)).toBe(true);
      expect(recommendation.depth).toBe(0);
    }
  });

  test("signal priority: firewall > trust > fidelity", async () => {
    const blockedButOtherwiseClean: AdvisorContext = {
      goal: "Do something",
      sanitizationResult: {
        content: "content",
        wasTruncated: false,
        injectionPatternsFound: ["system-role-token"],
        blocked: true,
        source: "test",
      },
      trustScore: {
        tier: TrustTier.LOCAL,
        score: 1.0,
        reason: "Local",
        domain: "local",
      },
      fidelityResult: {
        needsClarification: false,
        clarificationQuestion: null,
        interpretation: "Clear",
        gapChecks: [],
        canProceed: true,
        round: 0,
      },
    };

    const output = await decide(blockedButOtherwiseClean);
    expect(output.decision).toBe("abort");
  });

  test("max rounds reached — fidelity checker caps clarification, advisor proceeds", async () => {
    const maxRoundsReached: AdvisorContext = {
      goal: "Do something vague",
      fidelityResult: {
        needsClarification: false,
        clarificationQuestion: null,
        interpretation: "Vague but capped",
        gapChecks: ["scope: significant"],
        canProceed: true,
        round: 3,
      },
      round: 3,
    };

    const output = await decide(maxRoundsReached);
    expect(output.decision).toBe("proceed");
    expect(output.reason).toContain("Maximum clarification rounds");
    expect(output.confidence).toBe(0.67);
  });
});
