import { describe, test, expect } from "bun:test";
import {
  decideEscalation,
  createCostTracker,
  type AutoEscalationRequest,
} from "./auto-escalation.js";

describe("auto-escalation", () => {
  test("hard task is auto-escalated to stronger model", () => {
    const request: AutoEscalationRequest = {
      taskDescription:
        "Design a distributed architecture with security authentication and authorization",
    };

    const decision = decideEscalation(request);

    expect(decision.escalated).toBe(true);
    expect(decision.model).toBe("claude-opus");
    expect(decision.overridden).toBe(false);
    expect(decision.estimatedCostMultiplier).toBeGreaterThan(1);
    expect(decision.reason).toContain("escalated");
  });

  test("user override takes precedence over auto-escalation", () => {
    const request: AutoEscalationRequest = {
      taskDescription:
        "Design a distributed architecture with security and authorization",
      userOverrideModel: "gpt-4o",
    };

    const decision = decideEscalation(request);

    expect(decision.model).toBe("gpt-4o");
    expect(decision.escalated).toBe(false);
    expect(decision.overridden).toBe(true);
    expect(decision.reason).toContain("User override");
    expect(decision.estimatedCostMultiplier).toBe(1.0);
  });

  test("escalated tasks increase cost tracker", () => {
    const tracker = createCostTracker();
    const request: AutoEscalationRequest = {
      taskDescription:
        "Build distributed architecture with security authentication and scalability",
    };

    decideEscalation(request, tracker);

    expect(tracker.totalEscalations).toBe(1);
    expect(tracker.totalCostMultiplier).toBeGreaterThan(0);
  });

  test("simple task uses default model without escalation", () => {
    const request: AutoEscalationRequest = {
      taskDescription: "Fix typo in readme",
    };

    const decision = decideEscalation(request);

    expect(decision.escalated).toBe(false);
    expect(decision.model).toBe("claude-sonnet");
    expect(decision.overridden).toBe(false);
    expect(decision.estimatedCostMultiplier).toBe(1);
  });

  test("cost summary reflects multiple escalations", () => {
    const tracker = createCostTracker();

    decideEscalation(
      {
        taskDescription:
          "Distributed architecture with security and authentication",
      },
      tracker,
    );
    decideEscalation(
      {
        taskDescription:
          "Concurrency synchronization with parallel optimization algorithm",
      },
      tracker,
    );

    const summary = tracker.summary();
    expect(summary.totalEscalations).toBe(2);
    expect(summary.averageCostMultiplier).toBeGreaterThan(1);
  });

  test("non-escalated tasks do not affect cost tracker", () => {
    const tracker = createCostTracker();

    decideEscalation({ taskDescription: "Update readme file" }, tracker);

    expect(tracker.totalEscalations).toBe(0);
    expect(tracker.totalCostMultiplier).toBe(0);

    const summary = tracker.summary();
    expect(summary.averageCostMultiplier).toBe(1.0);
  });
});
