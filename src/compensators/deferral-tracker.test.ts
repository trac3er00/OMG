import { describe, expect, test } from "bun:test";

import { checkTaskCompletion, detectSilentDeferral } from "./deferral-tracker";

describe("detectSilentDeferral", () => {
  test("detects follow-up session deferral phrase", () => {
    const result = detectSilentDeferral(
      "Let's handle this in a follow-up session after shipping.",
    );

    expect(result.detected).toBe(true);
    expect(result.matchedPhrases.length).toBe(1);
    expect(result.warningMessage).toContain("Silent deferral detected");
  });

  test("detects multiple distinct deferral phrases", () => {
    const result = detectSilentDeferral(
      "This is out of scope for now and will be addressed later.",
    );

    expect(result.detected).toBe(true);
    expect(result.matchedPhrases.length).toBe(2);
    expect(result.warningMessage).toContain("2 pattern(s)");
  });

  test("matches TODO later style deferral", () => {
    const result = detectSilentDeferral(
      "TODO: revisit caching logic later when benchmarks are stable",
    );

    expect(result.detected).toBe(true);
    expect(result.matchedPhrases.some((p) => p.includes("TODO"))).toBe(true);
  });

  test("returns no warning when no deferral language exists", () => {
    const result = detectSilentDeferral(
      "Implemented all requested items and validated tests.",
    );

    expect(result.detected).toBe(false);
    expect(result.matchedPhrases).toEqual([]);
    expect(result.warningMessage).toBeUndefined();
  });
});

describe("checkTaskCompletion", () => {
  test("blocks when some declared tasks are incomplete", () => {
    const result = checkTaskCompletion({
      declaredTasks: ["A", "B", "C"],
      completedTasks: ["A", "C"],
    });

    expect(result.blocked).toBe(true);
    expect(result.incompleteTasks).toEqual(["B"]);
    expect(result.completionRatio).toBeCloseTo(2 / 3);
    expect(result.blockMessage).toContain("1 task(s) uncompleted");
  });

  test("does not block when all declared tasks are complete", () => {
    const result = checkTaskCompletion({
      declaredTasks: ["Task 1", "Task 2"],
      completedTasks: ["Task 1", "Task 2"],
    });

    expect(result.blocked).toBe(false);
    expect(result.incompleteTasks).toEqual([]);
    expect(result.completionRatio).toBe(1);
    expect(result.blockMessage).toBeUndefined();
  });

  test("uses ratio 1 when no declared tasks exist", () => {
    const result = checkTaskCompletion({
      declaredTasks: [],
      completedTasks: [],
    });

    expect(result.blocked).toBe(false);
    expect(result.incompleteTasks).toEqual([]);
    expect(result.completionRatio).toBe(1);
  });

  test("truncates block message task list after first three", () => {
    const result = checkTaskCompletion({
      declaredTasks: ["one", "two", "three", "four", "five"],
      completedTasks: [],
    });

    expect(result.blocked).toBe(true);
    expect(result.incompleteTasks).toEqual([
      "one",
      "two",
      "three",
      "four",
      "five",
    ]);
    expect(result.blockMessage).toContain("one, two, three...");
  });
});
