export interface AcceptanceCriterion {
  description: string;
  type: "functional" | "performance" | "security" | "compatibility";
}

export interface QAScenario {
  name: string;
  tool: "Bash" | "Playwright" | "curl" | "pytest" | "bun test";
  preconditions: string[];
  steps: string[];
  expectedResult: string;
  isHappyPath: boolean;
  isErrorCase: boolean;
}

export interface GeneratedQA {
  taskId: string;
  taskDescription: string;
  scenarios: QAScenario[];
  happyPathCount: number;
  errorCaseCount: number;
}

const TOOL_BY_TYPE: Record<AcceptanceCriterion["type"], QAScenario["tool"]> = {
  functional: "bun test",
  performance: "Bash",
  security: "Bash",
  compatibility: "Bash",
};

function pickTool(
  criterion: AcceptanceCriterion,
  description: string,
): QAScenario["tool"] {
  const lower = `${criterion.description} ${description}`.toLowerCase();
  if (
    lower.includes("browser") ||
    lower.includes("ui") ||
    lower.includes("page")
  )
    return "Playwright";
  if (
    lower.includes("endpoint") ||
    lower.includes("api") ||
    lower.includes("http")
  )
    return "curl";
  if (lower.includes("python") || lower.includes("pytest")) return "pytest";
  return TOOL_BY_TYPE[criterion.type];
}

function extractPreconditions(
  criterion: AcceptanceCriterion,
  taskDescription: string,
): string[] {
  const preconditions: string[] = [];
  const lower = `${criterion.description} ${taskDescription}`.toLowerCase();

  if (lower.includes("database") || lower.includes("db"))
    preconditions.push("Database is running and seeded with test data");
  if (lower.includes("server") || lower.includes("api"))
    preconditions.push("Application server is running on test port");
  if (lower.includes("auth") || lower.includes("login"))
    preconditions.push("Test user credentials are available");
  if (lower.includes("file") || lower.includes("config"))
    preconditions.push("Required configuration files exist");
  if (lower.includes("build") || lower.includes("compile"))
    preconditions.push("Project builds without errors");

  if (preconditions.length === 0) {
    preconditions.push("Project dependencies are installed");
  }

  return preconditions;
}

function generateHappyPathSteps(
  criterion: AcceptanceCriterion,
  tool: QAScenario["tool"],
): string[] {
  const base = criterion.description;

  switch (tool) {
    case "bun test":
      return [
        `Run: bun test --filter "${slugify(base)}"`,
        `Assert: test suite passes with 0 failures`,
        `Assert: ${base}`,
      ];
    case "Playwright":
      return [
        `Navigate to the relevant page`,
        `Perform action: ${base}`,
        `Assert: expected UI state is reached`,
        `Take screenshot for evidence`,
      ];
    case "curl":
      return [
        `Send request: curl -X GET/POST <endpoint>`,
        `Assert: HTTP status 2xx`,
        `Assert: response body matches: ${base}`,
      ];
    case "pytest":
      return [
        `Run: pytest -k "${slugify(base)}" -v`,
        `Assert: all collected tests pass`,
        `Assert: ${base}`,
      ];
    case "Bash":
      return [
        `Execute verification command for: ${base}`,
        `Assert: exit code 0`,
        `Assert: output confirms ${base}`,
      ];
  }
}

function generateErrorCaseSteps(
  criterion: AcceptanceCriterion,
  tool: QAScenario["tool"],
): string[] {
  const base = criterion.description;

  switch (tool) {
    case "bun test":
      return [
        `Run: bun test --filter "${slugify(base)}-error"`,
        `Provide invalid input or missing dependencies`,
        `Assert: error is handled gracefully (no crash)`,
        `Assert: meaningful error message is returned`,
      ];
    case "Playwright":
      return [
        `Navigate to the relevant page`,
        `Attempt invalid action (empty form, bad input)`,
        `Assert: validation error is displayed`,
        `Assert: page does not crash or show raw error`,
      ];
    case "curl":
      return [
        `Send malformed request: curl -X POST <endpoint> -d '{}'`,
        `Assert: HTTP status 4xx`,
        `Assert: error response includes descriptive message`,
      ];
    case "pytest":
      return [
        `Run: pytest -k "${slugify(base)}-negative" -v`,
        `Assert: expected failures are captured`,
        `Assert: no unhandled exceptions`,
      ];
    case "Bash":
      return [
        `Execute command with invalid arguments`,
        `Assert: non-zero exit code`,
        `Assert: stderr contains actionable error message`,
      ];
  }
}

/**
 * Generate QA scenarios from task description and acceptance criteria.
 * Always generates at least 1 happy path and 1 error case.
 */
export function generateQAScenarios(
  taskId: string,
  taskDescription: string,
  acceptanceCriteria: AcceptanceCriterion[],
): GeneratedQA {
  const scenarios: QAScenario[] = [];

  for (const criterion of acceptanceCriteria) {
    const tool = pickTool(criterion, taskDescription);
    const preconditions = extractPreconditions(criterion, taskDescription);

    scenarios.push({
      name: `[Happy] ${criterion.description}`,
      tool,
      preconditions,
      steps: generateHappyPathSteps(criterion, tool),
      expectedResult: `${criterion.description} is verified successfully`,
      isHappyPath: true,
      isErrorCase: false,
    });

    scenarios.push({
      name: `[Error] ${criterion.description} — negative case`,
      tool,
      preconditions,
      steps: generateErrorCaseSteps(criterion, tool),
      expectedResult: `Error is handled gracefully with clear feedback`,
      isHappyPath: false,
      isErrorCase: true,
    });
  }

  if (scenarios.filter((s) => s.isHappyPath).length === 0) {
    scenarios.push(fallbackHappyPath(taskId, taskDescription));
  }
  if (scenarios.filter((s) => s.isErrorCase).length === 0) {
    scenarios.push(fallbackErrorCase(taskId, taskDescription));
  }

  return {
    taskId,
    taskDescription,
    scenarios,
    happyPathCount: scenarios.filter((s) => s.isHappyPath).length,
    errorCaseCount: scenarios.filter((s) => s.isErrorCase).length,
  };
}

/** Format generated QA as markdown for embedding in plan files. */
export function formatQAAsMarkdown(qa: GeneratedQA): string {
  const lines: string[] = [];

  lines.push(`## QA Scenarios: ${qa.taskId}`);
  lines.push("");
  lines.push(`**Task:** ${qa.taskDescription}`);
  lines.push("");
  lines.push(
    `**Coverage:** ${qa.happyPathCount} happy-path, ${qa.errorCaseCount} error-case`,
  );
  lines.push("");

  for (const scenario of qa.scenarios) {
    lines.push(`### ${scenario.name}`);
    lines.push("");
    lines.push(`- **Tool:** \`${scenario.tool}\``);

    if (scenario.preconditions.length > 0) {
      lines.push(`- **Preconditions:**`);
      for (const pre of scenario.preconditions) {
        lines.push(`  - ${pre}`);
      }
    }

    lines.push(`- **Steps:**`);
    for (let i = 0; i < scenario.steps.length; i++) {
      lines.push(`  ${i + 1}. ${scenario.steps[i]}`);
    }

    lines.push(`- **Expected:** ${scenario.expectedResult}`);
    lines.push("");
  }

  return lines.join("\n");
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
}

function fallbackHappyPath(taskId: string, description: string): QAScenario {
  return {
    name: `[Happy] ${taskId} basic verification`,
    tool: "bun test",
    preconditions: ["Project dependencies are installed"],
    steps: [
      `Run: bun test --filter "${slugify(description)}"`,
      `Assert: test suite passes with 0 failures`,
      `Assert: feature described as "${description}" works correctly`,
    ],
    expectedResult: "Basic functionality verified",
    isHappyPath: true,
    isErrorCase: false,
  };
}

function fallbackErrorCase(taskId: string, _description: string): QAScenario {
  return {
    name: `[Error] ${taskId} invalid input handling`,
    tool: "bun test",
    preconditions: ["Project dependencies are installed"],
    steps: [
      `Provide invalid or missing input to the feature`,
      `Assert: no unhandled exception or crash`,
      `Assert: meaningful error message is returned`,
    ],
    expectedResult: "Error handled gracefully with clear feedback",
    isHappyPath: false,
    isErrorCase: true,
  };
}
