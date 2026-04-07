import { describe, expect, test } from "bun:test";

import {
  DEFAULT_ESCALATION_CONFIG,
  EscalationTracker,
  getEscalationResult,
} from "./escalation.js";

describe("escalation", () => {
  test("hard subtask routes to stronger model", () => {
    const result = getEscalationResult({
      description:
        "Design architecture for secure multi-model orchestration with algorithmic verification",
    });

    expect(result.escalated).toBe(true);
    expect(result.model).toBe(DEFAULT_ESCALATION_CONFIG.escalatedModel);
    expect(result.evidence.complexity).toBe("hard");
  });

  test("simple task stays on default model", () => {
    const result = getEscalationResult({
      description: "Rename a variable in a tiny helper",
    });

    expect(result.escalated).toBe(false);
    expect(result.model).toBe(DEFAULT_ESCALATION_CONFIG.defaultModel);
    expect(result.estimatedCostMultiplier).toBe(1);
  });

  test("cost tracking records multiplier and frequency for escalated tasks", () => {
    const tracker = new EscalationTracker();

    const first = tracker.evaluateTask({
      description:
        "Build architecture for secure distributed orchestration and algorithm optimization",
    });
    const second = tracker.evaluateTask({
      description: "Add a small comment to the CLI help text",
    });

    expect(first.estimatedCostMultiplier).toBeGreaterThan(1);
    expect(first.budget.escalationCount).toBe(1);
    expect(second.budget.escalationCount).toBe(1);
    expect(tracker.getEvidence()).toHaveLength(2);
    expect(tracker.getEvidence()[0]?.escalated).toBe(true);
  });

  test("disabled escalation keeps default model", () => {
    const result = getEscalationResult(
      {
        description: "Plan security architecture for a complex migration",
      },
      {
        ...DEFAULT_ESCALATION_CONFIG,
        enabled: false,
      },
    );

    expect(result.escalated).toBe(false);
    expect(result.model).toBe(DEFAULT_ESCALATION_CONFIG.defaultModel);
    expect(result.evidence.escalated).toBe(false);
  });
});
