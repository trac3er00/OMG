import { describe, test, expect } from "bun:test";
import { shouldTriggerAdvisor } from "./triggers.js";
import type { IntentAnalysis } from "../intent/index.js";

function makeIntent(
  overrides: Partial<IntentAnalysis & { _advisorGenerated?: boolean }>,
): IntentAnalysis & { _advisorGenerated?: boolean } {
  return {
    intent: "trivial",
    domain: "other",
    complexity: {
      filesAffected: 1,
      effort: "low",
      riskLevel: "low",
      signals: [],
    },
    ambiguities: [],
    suggestedApproach: "",
    clarifyingQuestions: [],
    confidenceScore: 1.0,
    ...overrides,
  };
}

describe("shouldTriggerAdvisor", () => {
  test("triggers for architectural intent", () => {
    const intent = makeIntent({
      intent: "architectural",
      complexity: {
        filesAffected: 9,
        effort: "high",
        riskLevel: "high",
        signals: ["architecture-signal"],
      },
    });
    expect(shouldTriggerAdvisor(intent)).toBe(true);
  });

  test("does not trigger for trivial intent", () => {
    const intent = makeIntent({ intent: "trivial" });
    expect(shouldTriggerAdvisor(intent)).toBe(false);
  });

  test("does not trigger when _advisorGenerated is true", () => {
    const intent = makeIntent({
      intent: "architectural",
      _advisorGenerated: true,
    });
    expect(shouldTriggerAdvisor(intent)).toBe(false);
  });

  test("does not trigger beyond depth limit", () => {
    const intent = makeIntent({ intent: "architectural" });
    expect(shouldTriggerAdvisor(intent, 2)).toBe(false);
  });

  test("triggers for high-risk complex intent", () => {
    const intent = makeIntent({
      intent: "complex",
      complexity: {
        filesAffected: 6,
        effort: "high",
        riskLevel: "high",
        signals: [],
      },
    });
    expect(shouldTriggerAdvisor(intent)).toBe(true);
  });
});
