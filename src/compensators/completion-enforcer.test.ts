import { describe, expect, test } from "bun:test";

import { enforceChecklist, enforceCompletion } from "./completion-enforcer";

describe("enforceCompletion", () => {
  test("approves when completion is not claimed", () => {
    const result = enforceCompletion({
      taskId: "T1",
      claimed: false,
      testsPassed: false,
    });

    expect(result.approved).toBe(true);
    expect(result.violations).toHaveLength(0);
    expect(result.message).toBeUndefined();
  });

  test("rejects claimed completion with no evidence files", () => {
    const result = enforceCompletion({
      taskId: "T2",
      claimed: true,
      evidenceFiles: [],
    });

    expect(result.approved).toBe(false);
    expect(result.violations).toContain(
      "no_evidence_for_claim: Completion claimed without evidence files",
    );
  });

  test("rejects claimed completion when tests are failing", () => {
    const result = enforceCompletion({
      taskId: "T3",
      claimed: true,
      evidenceFiles: ["report.txt"],
      testsPassed: false,
    });

    expect(result.approved).toBe(false);
    expect(result.violations).toContain(
      "tests_failing: Cannot claim completion when tests are failing",
    );
  });

  test("aggregates both violations when both conditions fail", () => {
    const result = enforceCompletion({
      taskId: "T4",
      claimed: true,
      testsPassed: false,
    });

    expect(result.approved).toBe(false);
    expect(result.violations).toHaveLength(2);
    expect(result.message).toContain("Completion rejected:");
    expect(result.message).toContain("no_evidence_for_claim");
    expect(result.message).toContain("tests_failing");
  });

  test("approves claimed completion with evidence and passing tests", () => {
    const result = enforceCompletion({
      taskId: "T5",
      claimed: true,
      evidenceFiles: ["trace.json", "summary.md"],
      testsPassed: true,
    });

    expect(result.approved).toBe(true);
    expect(result.violations).toHaveLength(0);
    expect(result.message).toBeUndefined();
  });
});

describe("enforceChecklist", () => {
  test("approves when all required items are completed", () => {
    const result = enforceChecklist([
      { id: "lint", required: true, completed: true },
      { id: "docs", required: false, completed: false },
    ]);

    expect(result.approved).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  test("approves required item skipped with reason", () => {
    const result = enforceChecklist([
      {
        id: "security-review",
        required: true,
        completed: false,
        skippedReason: "waived",
      },
    ]);

    expect(result.approved).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  test("rejects required item skipped without reason", () => {
    const result = enforceChecklist([
      { id: "integration-tests", required: true, completed: false },
    ]);

    expect(result.approved).toBe(false);
    expect(result.violations).toEqual([
      'category_skip: Required item "integration-tests" skipped without reason',
    ]);
    expect(result.message).toBe(
      "Checklist incomplete: 1 item(s) skipped without reason",
    );
  });

  test("collects multiple checklist violations", () => {
    const result = enforceChecklist([
      { id: "build", required: true, completed: false },
      { id: "release-notes", required: true, completed: false },
    ]);

    expect(result.approved).toBe(false);
    expect(result.violations).toHaveLength(2);
    expect(result.message).toBe(
      "Checklist incomplete: 2 item(s) skipped without reason",
    );
  });
});
