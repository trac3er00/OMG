import { describe, expect, test } from "bun:test";

import {
  createTraceLink,
  extractTaskReference,
  formatWithTaskRef,
  generateTraceabilityReport,
} from "./traceability.js";

describe("extractTaskReference", () => {
  test("extract-ref: [T14] → T14", () => {
    expect(extractTaskReference("[T14] feat: add feature")).toBe("T14");
  });

  test("extract-ref: task-14 → T14", () => {
    expect(extractTaskReference("fix: resolve task-14 issue")).toBe("T14");
  });

  test("extract-ref: feat(T7): → T7", () => {
    expect(extractTaskReference("feat(T7): add planning")).toBe("T7");
  });

  test("extract-ref: bare T3 → T3", () => {
    expect(extractTaskReference("chore: update T3 deps")).toBe("T3");
  });

  test("extract-ref: case insensitive [t14]", () => {
    expect(extractTaskReference("[t14] lowercase tag")).toBe("T14");
  });

  test("extract-ref-none: no task reference → null", () => {
    expect(extractTaskReference("fix: typo")).toBeNull();
  });

  test("extract-ref-none: empty string → null", () => {
    expect(extractTaskReference("")).toBeNull();
  });
});

describe("createTraceLink", () => {
  test("creates link with all fields", () => {
    const link = createTraceLink("T14", "abc123", "feat: add [T14]", [
      "src/foo.ts",
    ]);
    expect(link.taskId).toBe("T14");
    expect(link.commitHash).toBe("abc123");
    expect(link.commitMessage).toBe("feat: add [T14]");
    expect(link.files).toEqual(["src/foo.ts"]);
    expect(link.timestamp).toBeTruthy();
  });

  test("defaults files to empty array", () => {
    const link = createTraceLink("T1", "def456", "fix: patch");
    expect(link.files).toEqual([]);
  });
});

describe("formatWithTaskRef", () => {
  test("format-ref: appends task reference", () => {
    const result = formatWithTaskRef("feat: add feature", "T14");
    expect(result).toBe("feat: add feature [T14]");
  });

  test("format-ref: handles numeric-only taskId", () => {
    const result = formatWithTaskRef("fix: bug", "14");
    expect(result).toBe("fix: bug [T14]");
  });

  test("format-ref: idempotent when already present", () => {
    const msg = "feat: add feature [T14]";
    expect(formatWithTaskRef(msg, "T14")).toBe(msg);
  });
});

describe("generateTraceabilityReport", () => {
  test("report: produces valid report with links", () => {
    const links = [
      createTraceLink("T1", "aaa", "feat: init [T1]", ["src/a.ts"]),
      createTraceLink("T3", "bbb", "fix: patch [T3]"),
    ];
    const allTasks = ["T1", "T2", "T3", "T4"];

    const report = generateTraceabilityReport("plan-alpha", links, allTasks);

    expect(report.planId).toBe("plan-alpha");
    expect(report.generatedAt).toBeTruthy();
    expect(report.links).toHaveLength(2);
    expect(report.tasksWithCommits).toEqual(["T1", "T3"]);
    expect(report.tasksWithoutCommits).toEqual(["T2", "T4"]);
  });

  test("report: empty links → all tasks without commits", () => {
    const report = generateTraceabilityReport("plan-beta", [], ["T1", "T2"]);
    expect(report.tasksWithCommits).toEqual([]);
    expect(report.tasksWithoutCommits).toEqual(["T1", "T2"]);
  });

  test("bidirectional: plan task links to commits AND commits link back", () => {
    const link = createTraceLink("T5", "ccc", "feat(T5): add search");
    const report = generateTraceabilityReport(
      "plan-gamma",
      [link],
      ["T5", "T6"],
    );

    expect(report.tasksWithCommits).toContain("T5");

    const ref = extractTaskReference(link.commitMessage);
    expect(ref).toBe("T5");
    expect(report.links[0]?.taskId).toBe(ref as string);
  });
});
