import { describe, expect, test } from "bun:test";

import { understandIntent } from "../intent/index.js";
import { ProactiveExecutor } from "./proactive.js";

describe("ProactiveExecutor", () => {
  const executor = new ProactiveExecutor();

  test("fix typo in button executes immediately", () => {
    const intent = understandIntent("fix typo in button");

    expect(executor.shouldExecuteImmediately(intent)).toBe(true);

    const decision = executor.execute(intent, { prompt: "fix typo in button" });
    expect(decision.mode).toBe("execute");
    expect(decision.executeImmediately).toBe(true);
    expect(decision.clarifyingQuestion).toBeNull();
    expect(decision.showPlan).toBe(false);
  });

  test("do something with auth asks exactly one clarifying question", () => {
    const intent = understandIntent("do something with auth");
    const question = executor.shouldAskClarification(intent);

    expect(question).not.toBeNull();
    expect(question).toEqual({
      question: "What exact outcome should change when this task is complete?",
      reason: expect.any(String),
    });
    expect(Object.keys(question!)).toHaveLength(2);

    const decision = executor.execute(intent);
    expect(decision.mode).toBe("clarify");
    expect(decision.executeImmediately).toBe(false);
    expect(decision.showPlan).toBe(false);
    expect(decision.clarifyingQuestion).toEqual(question);
  });

  test("delete all user data shows a plan", () => {
    const intent = understandIntent("delete all user data");

    expect(intent.complexity.riskLevel).toBe("high");
    expect(executor.shouldShowPlan(intent)).toBe(true);

    const decision = executor.execute(intent);
    expect(decision.mode).toBe("plan");
    expect(decision.executeImmediately).toBe(false);
    expect(decision.showPlan).toBe(true);
    expect(decision.plan).not.toBeNull();
  });
});
