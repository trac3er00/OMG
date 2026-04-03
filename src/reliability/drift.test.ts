import { describe, expect, test } from "bun:test";

import { computeASI, type SessionObservation } from "./drift";

function obs(partial: Partial<SessionObservation> = {}): SessionObservation {
  const observation: SessionObservation = {
    timestamp: partial.timestamp ?? Date.now(),
    goal: partial.goal ?? "stabilize output quality",
    output: partial.output ?? "stabilize output quality",
  };

  if (partial.consensusScore !== undefined) {
    observation.consensusScore = partial.consensusScore;
  }

  if (partial.toolsUsed !== undefined) {
    observation.toolsUsed = partial.toolsUsed;
  }

  return observation;
}

describe("computeASI", () => {
  test("returns no drift for fewer than two observations", () => {
    const report = computeASI([obs()]);

    expect(report.detected).toBe(false);
    expect(report.scores.semanticDrift).toBe(0);
    expect(report.scores.coordinationDrift).toBe(0);
    expect(report.scores.behavioralDrift).toBe(0);
    expect(report.scores.asi).toBe(1);
    expect(typeof report.timestamp).toBe("number");
  });

  test("computes semantic drift from early vs late alignment", () => {
    const report = computeASI([
      obs({ goal: "build robust parser", output: "build robust parser quickly" }),
      obs({ goal: "build robust parser", output: "build robust parser safely" }),
      obs({ goal: "build robust parser", output: "completely unrelated weather summary" }),
      obs({ goal: "build robust parser", output: "totally different gardening advice" }),
    ]);

    expect(report.scores.semanticDrift).toBeGreaterThan(0);
    expect(report.scores.semanticDrift).toBeCloseTo(1, 5);
  });

  test("computes coordination drift as inverse average consensus", () => {
    const report = computeASI([
      obs({ consensusScore: 0.9 }),
      obs({ consensusScore: 0.6 }),
      obs({ consensusScore: 0.5 }),
      obs({ consensusScore: 0.8 }),
    ]);

    // average = 0.7 => drift = 0.3
    expect(report.scores.coordinationDrift).toBeCloseTo(0.3, 8);
  });

  test("coordination drift is zero when no consensus scores are provided", () => {
    const report = computeASI([obs({}), obs({}), obs({})]);

    expect(report.scores.coordinationDrift).toBe(0);
  });

  test("computes behavioral drift from new late-stage tools", () => {
    const report = computeASI([
      obs({ toolsUsed: ["read", "write"] }),
      obs({ toolsUsed: ["read"] }),
      obs({ toolsUsed: ["read", "grep", "lsp"] }),
      obs({ toolsUsed: ["write", "grep"] }),
    ]);

    // early unique tools = {read, write}
    // late new tools occurrences = [grep, lsp, grep] => 3
    // all tools in denominator = {read, write, grep, lsp} => 4
    expect(report.scores.behavioralDrift).toBeCloseTo(0.75, 8);
  });

  test("detects dominant drift type and sets message when max drift > 0.5", () => {
    const report = computeASI([
      obs({ toolsUsed: ["read"] }),
      obs({ toolsUsed: ["read"] }),
      obs({ toolsUsed: ["newA", "newB", "newC"] }),
      obs({ toolsUsed: ["newD"] }),
    ]);

    expect(report.detected).toBe(true);
    expect(report.dominantDriftType).toBe("behavioral");
    expect(report.message).toContain("Agent drift detected");
    expect(report.message).toContain("Dominant: behavioral");
  });

  test("keeps detection false when all drifts are low", () => {
    const report = computeASI([
      obs({ goal: "improve reliability", output: "improve reliability", consensusScore: 1, toolsUsed: ["read"] }),
      obs({ goal: "improve reliability", output: "improve reliability", consensusScore: 1, toolsUsed: ["read"] }),
      obs({ goal: "improve reliability", output: "improve reliability", consensusScore: 1, toolsUsed: ["read"] }),
      obs({ goal: "improve reliability", output: "improve reliability", consensusScore: 1, toolsUsed: ["read"] }),
    ]);

    expect(report.detected).toBe(false);
    expect(report.scores.semanticDrift).toBe(0);
    expect(report.scores.coordinationDrift).toBe(0);
    expect(report.scores.behavioralDrift).toBe(0);
    expect(report.scores.asi).toBe(1);
    expect(report.dominantDriftType).toBeUndefined();
    expect(report.message).toBeUndefined();
  });

  test("uses floor split for odd observation counts", () => {
    const report = computeASI([
      obs({ toolsUsed: ["read"] }),
      obs({ toolsUsed: ["new1"] }),
      obs({ toolsUsed: ["new2"] }),
    ]);

    // half=floor(3/2)=1 => early={read}, lateNew=[new1,new2], all={read,new1,new2}
    expect(report.scores.behavioralDrift).toBeCloseTo(2 / 3, 8);
  });
});
