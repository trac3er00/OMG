import { describe, expect, test } from "bun:test";

import { evaluateWithCompensators } from "./pipeline";

describe("evaluateWithCompensators", () => {
  test("approves empty input when no checks are triggered", () => {
    const result = evaluateWithCompensators({});

    expect(result.verdict).toBe("APPROVE");
    expect(result.checks).toHaveLength(0);
    expect(result.reasons).toHaveLength(0);
  });

  test("rejects when trailing off is detected", () => {
    const result = evaluateWithCompensators({
      taskItems: [
        { id: "t1", content: "a", lineCount: 50 },
        { id: "t2", content: "b", lineCount: 52 },
        { id: "t3", content: "c", lineCount: 49 },
        { id: "t4", content: "d", lineCount: 6 },
        { id: "t5", content: "e", lineCount: 5 },
      ],
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("trailing_off_detected");
    expect(
      result.checks.find((check) => check.name === "trailing_off")?.passed,
    ).toBe(false);
  });

  test("rejects deferral language in output text", () => {
    const result = evaluateWithCompensators({
      outputText: "We'll finish this in a future session.",
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("silent_deferral_detected");
  });

  test("rejects incomplete task completion state", () => {
    const result = evaluateWithCompensators({
      taskState: {
        declaredTasks: ["T1", "T2"],
        completedTasks: ["T1"],
      },
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("task_completion_blocked");
  });

  test("rejects merge contradiction across agent outputs", () => {
    const result = evaluateWithCompensators({
      agentOutputs: [
        { agentId: "a1", claim: "Enable JWT auth", confidence: 0.8 },
        { agentId: "a2", claim: "Disable JWT auth", confidence: 0.9 },
      ],
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("merge_contradiction_detected");
  });

  test("rejects completion claim without evidence", () => {
    const result = evaluateWithCompensators({
      claim: {
        taskId: "T100",
        claimed: true,
        evidenceFiles: [],
        testsPassed: true,
      },
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("completion_claim_rejected");
  });

  test("approves when all provided compensators are clean", () => {
    const result = evaluateWithCompensators({
      taskItems: [
        { id: "t1", content: "a", lineCount: 40 },
        { id: "t2", content: "b", lineCount: 42 },
        { id: "t3", content: "c", lineCount: 41 },
        { id: "t4", content: "d", lineCount: 39 },
        { id: "t5", content: "e", lineCount: 40 },
      ],
      outputText: "Completed all requested steps.",
      readStats: { totalLines: 200, linesRead: 200 },
      taskState: {
        declaredTasks: ["T1", "T2", "T3"],
        completedTasks: ["T1", "T2", "T3"],
      },
      agentOutputs: [
        { agentId: "a1", claim: "Use JWT auth", confidence: 0.9 },
        { agentId: "a2", claim: "Add role checks", confidence: 0.85 },
      ],
      claim: {
        taskId: "T200",
        claimed: true,
        evidenceFiles: ["proof.log"],
        testsPassed: true,
      },
      checklistItems: [
        { id: "build", required: true, completed: true },
        { id: "docs", required: false, completed: false },
      ],
      checklistStats: { totalItems: 3, checkedItems: 3 },
    });

    expect(result.verdict).toBe("APPROVE");
    expect(result.reasons).toHaveLength(0);
    expect(result.checks.every((check) => check.passed)).toBe(true);
  });

  test("rejects with multiple reasons when multiple compensators fail", () => {
    const result = evaluateWithCompensators({
      outputText: "Showing first 10 lines only; will be addressed later.",
      readStats: { totalLines: 100, linesRead: 20 },
      claim: {
        taskId: "T300",
        claimed: true,
        testsPassed: false,
      },
    });

    expect(result.verdict).toBe("REJECT");
    expect(result.reasons).toContain("courtesy_cut_detected");
    expect(result.reasons).toContain("silent_deferral_detected");
    expect(result.reasons).toContain("read_incomplete");
    expect(result.reasons).toContain("completion_claim_rejected");
    expect(result.reasons.length).toBeGreaterThan(3);
  });
});
