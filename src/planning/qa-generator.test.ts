import { describe, expect, test } from "bun:test";

import { formatQAAsMarkdown, generateQAScenarios } from "./qa-generator.js";
import type { AcceptanceCriterion } from "./qa-generator.js";

const CRITERIA: AcceptanceCriterion[] = [
  { description: "User can submit the form", type: "functional" },
  { description: "Page loads within 2 seconds", type: "performance" },
];

describe("generateQAScenarios", () => {
  test("generates scenarios from task with acceptance criteria", () => {
    const qa = generateQAScenarios("task-1", "Build login page", CRITERIA);

    expect(qa.taskId).toBe("task-1");
    expect(qa.taskDescription).toBe("Build login page");
    expect(qa.scenarios.length).toBeGreaterThanOrEqual(2);
  });

  test("at least 1 happy path scenario generated", () => {
    const qa = generateQAScenarios("task-2", "Add search feature", CRITERIA);

    expect(qa.happyPathCount).toBeGreaterThanOrEqual(1);
    expect(qa.scenarios.some((s) => s.isHappyPath)).toBe(true);
  });

  test("at least 1 error case scenario generated", () => {
    const qa = generateQAScenarios("task-3", "Add payment flow", CRITERIA);

    expect(qa.errorCaseCount).toBeGreaterThanOrEqual(1);
    expect(qa.scenarios.some((s) => s.isErrorCase)).toBe(true);
  });

  test("generated steps are non-empty concrete strings", () => {
    const qa = generateQAScenarios("task-4", "Create dashboard", CRITERIA);

    for (const scenario of qa.scenarios) {
      expect(scenario.steps.length).toBeGreaterThan(0);
      for (const step of scenario.steps) {
        expect(typeof step).toBe("string");
        expect(step.length).toBeGreaterThan(5);
      }
      expect(scenario.name.length).toBeGreaterThan(0);
      expect(scenario.expectedResult.length).toBeGreaterThan(0);
      expect(scenario.preconditions.length).toBeGreaterThan(0);
    }
  });

  test("empty criteria still produces fallback happy + error scenarios", () => {
    const qa = generateQAScenarios("task-5", "Misc work", []);

    expect(qa.happyPathCount).toBeGreaterThanOrEqual(1);
    expect(qa.errorCaseCount).toBeGreaterThanOrEqual(1);
    expect(qa.scenarios.length).toBe(2);
  });

  test("tool selection heuristic picks Playwright for browser criteria", () => {
    const browserCriteria: AcceptanceCriterion[] = [
      { description: "Browser displays the modal", type: "functional" },
    ];
    const qa = generateQAScenarios("task-6", "Modal feature", browserCriteria);
    const happy = qa.scenarios.find((s) => s.isHappyPath);

    expect(happy?.tool).toBe("Playwright");
  });

  test("tool selection heuristic picks curl for API criteria", () => {
    const apiCriteria: AcceptanceCriterion[] = [
      { description: "API endpoint returns 200", type: "functional" },
    ];
    const qa = generateQAScenarios("task-7", "REST endpoint", apiCriteria);
    const happy = qa.scenarios.find((s) => s.isHappyPath);

    expect(happy?.tool).toBe("curl");
  });

  test("security criteria get Bash tool by default", () => {
    const secCriteria: AcceptanceCriterion[] = [
      { description: "No SQL injection possible", type: "security" },
    ];
    const qa = generateQAScenarios("task-8", "Secure input", secCriteria);
    const happy = qa.scenarios.find((s) => s.isHappyPath);

    expect(happy?.tool).toBe("Bash");
  });

  test("preconditions include relevant context for db tasks", () => {
    const dbCriteria: AcceptanceCriterion[] = [
      { description: "Database stores the record", type: "functional" },
    ];
    const qa = generateQAScenarios("task-9", "Save record", dbCriteria);
    const scenario = qa.scenarios[0];

    expect(
      scenario.preconditions.some((p) => p.toLowerCase().includes("database")),
    ).toBe(true);
  });

  test("counts match actual scenario breakdown", () => {
    const qa = generateQAScenarios("task-10", "Full feature", CRITERIA);

    const actualHappy = qa.scenarios.filter((s) => s.isHappyPath).length;
    const actualError = qa.scenarios.filter((s) => s.isErrorCase).length;
    expect(qa.happyPathCount).toBe(actualHappy);
    expect(qa.errorCaseCount).toBe(actualError);
  });
});

describe("formatQAAsMarkdown", () => {
  test("produces valid markdown with headers", () => {
    const qa = generateQAScenarios("task-md", "Markdown test", CRITERIA);
    const md = formatQAAsMarkdown(qa);

    expect(md).toContain("## QA Scenarios: task-md");
    expect(md).toContain("**Task:** Markdown test");
    expect(md).toContain("**Coverage:**");
    expect(md).toContain("###");
  });

  test("markdown includes tool, steps, and expected result", () => {
    const qa = generateQAScenarios("task-md2", "Feature X", CRITERIA);
    const md = formatQAAsMarkdown(qa);

    expect(md).toContain("**Tool:**");
    expect(md).toContain("**Steps:**");
    expect(md).toContain("**Expected:**");
  });

  test("markdown includes preconditions section", () => {
    const qa = generateQAScenarios("task-md3", "Database feature", [
      { description: "Database migration runs", type: "functional" },
    ]);
    const md = formatQAAsMarkdown(qa);

    expect(md).toContain("**Preconditions:**");
  });

  test("empty criteria fallback still produces valid markdown", () => {
    const qa = generateQAScenarios("task-md4", "Empty", []);
    const md = formatQAAsMarkdown(qa);

    expect(md).toContain("## QA Scenarios: task-md4");
    expect(md).toContain("###");
    expect(md.length).toBeGreaterThan(50);
  });
});
