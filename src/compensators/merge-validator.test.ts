import { describe, expect, test } from "bun:test";

import type { AgentOutput } from "./merge-validator";
import { validateMerge } from "./merge-validator";

function out(agentId: string, claim: string, confidence = 0.9): AgentOutput {
  return { agentId, claim, confidence };
}

describe("validateMerge", () => {
  test("returns clean result when there are no outputs", () => {
    const result = validateMerge([]);

    expect(result.hasContradiction).toBe(false);
    expect(result.contradictions).toHaveLength(0);
    expect(result.validatedOutputs).toEqual([]);
    expect(result.warningMessage).toBeUndefined();
  });

  test("detects jwt vs session contradiction", () => {
    const outputs = [
      out("a", "Use JWT-based auth"),
      out("b", "Prefer session cookie auth"),
    ];
    const result = validateMerge(outputs);

    expect(result.hasContradiction).toBe(true);
    expect(result.contradictions).toHaveLength(1);
    expect(result.contradictions[0]?.reason).toBe(
      'Opposing: "jwt" vs "session"',
    );
    expect(result.warningMessage).toBe("1 contradictions detected.");
  });

  test("is case-insensitive for opposing terms", () => {
    const outputs = [
      out("a", "ENABLE feature flags now"),
      out("b", "we should disable this flow"),
    ];
    const result = validateMerge(outputs);

    expect(result.hasContradiction).toBe(true);
    expect(result.contradictions).toHaveLength(1);
    expect(result.contradictions[0]?.reason).toBe(
      'Opposing: "enable" vs "disable"',
    );
  });

  test("detects multiple contradictions across different pairs", () => {
    const outputs = [
      out("a", "Add retry policy for requests"),
      out("b", "Remove retry policy from pipeline"),
      out("c", "Increase worker count"),
      out("d", "Decrease worker count"),
    ];
    const result = validateMerge(outputs);

    expect(result.hasContradiction).toBe(true);
    expect(result.contradictions).toHaveLength(2);
    expect(result.warningMessage).toBe("2 contradictions detected.");
  });

  test("returns original outputs array as validatedOutputs", () => {
    const outputs = [out("a", "Ship implementation as async job")];
    const result = validateMerge(outputs);

    expect(result.validatedOutputs).toBe(outputs);
  });

  test("records at most one contradiction per output pair", () => {
    const outputs = [
      out("a", "Use JWT and enable async sync mode"),
      out("b", "Avoid session and disable async sync mode"),
    ];
    const result = validateMerge(outputs);

    expect(result.contradictions).toHaveLength(1);
  });
});
