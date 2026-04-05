export interface QualityCheckResult {
  readonly passed: readonly string[];
  readonly failed: readonly string[];
  readonly skipped: readonly string[];
  readonly issues: readonly string[];
}

export interface QualityStep {
  readonly name: string;
  readonly command: string;
}

export interface QualityRunnerDeps {
  readonly runCommand: (
    argv: readonly string[],
    cwd: string,
    timeoutMs: number,
  ) => Promise<{ exitCode: number; stdout: string; stderr: string }>;
  readonly readJson: (path: string) => Promise<Record<string, unknown> | null>;
  readonly exists: (path: string) => Promise<boolean>;
}

const QUALITY_STEPS: readonly string[] = ["format", "lint", "typecheck", "test"];

const ALLOWED_PREFIXES: readonly (readonly string[])[] = [
  ["npm", "test"], ["yarn", "test"], ["pnpm", "test"], ["bun", "test"],
  ["npx", "--no-install", "prettier"], ["npx", "--no-install", "eslint"],
  ["npx", "--no-install", "tsc"], ["npx", "--no-install", "jest"],
  ["npx", "--no-install", "vitest"], ["npx", "--no-install", "biome"],
  ["jest"], ["vitest"], ["eslint"], ["prettier"], ["tsc"], ["biome"],
  ["pytest"], ["python", "-m", "pytest"], ["python3", "-m", "pytest"],
  ["ruff"], ["mypy"], ["flake8"], ["black"], ["isort"], ["bandit"], ["pylint"],
  ["go", "test"], ["go", "vet"], ["go", "build"], ["golangci-lint"],
  ["cargo", "test"], ["cargo", "check"], ["cargo", "build"],
  ["cargo", "clippy"], ["cargo", "fmt"],
  ["shellcheck"],
];

const BLOCKED_PATTERNS: readonly string[] = [
  "&&", "||", "|", ";", "`", "$(", "${", ">", "<", "\n",
  "rm ", "curl ", "wget ", "eval ", "exec ", "sudo ",
];

export function isSafeCommand(cmd: string): { safe: boolean; reason: string; argv: readonly string[] } {
  const trimmed = cmd.trim();
  const cmdLower = trimmed.toLowerCase();

  for (const pattern of BLOCKED_PATTERNS) {
    const hasAlpha = /[a-z]/i.test(pattern);
    const target = hasAlpha ? cmdLower : trimmed;
    if (target.includes(pattern)) {
      return { safe: false, reason: `blocked pattern '${pattern}'`, argv: [] };
    }
  }

  const argv = splitCommand(trimmed);
  if (argv.length === 0) {
    return { safe: false, reason: "empty command", argv: [] };
  }

  for (const prefix of ALLOWED_PREFIXES) {
    if (argv.length < prefix.length) continue;
    const match = prefix.every((tok, i) => argv[i] === tok);
    if (match) {
      return { safe: true, reason: "", argv };
    }
  }

  return { safe: false, reason: "not in allowed commands list", argv: [] };
}

export class QualityRunner {
  private readonly deps: QualityRunnerDeps;

  constructor(deps: QualityRunnerDeps) {
    this.deps = deps;
  }

  async runChecks(
    projectDir: string,
    configPath?: string,
  ): Promise<QualityCheckResult> {
    const passed: string[] = [];
    const failed: string[] = [];
    const skipped: string[] = [];
    const issues: string[] = [];

    const qgPath = configPath ?? `${projectDir}/.omg/state/quality-gate.json`;
    const exists = await this.deps.exists(qgPath);
    if (!exists) {
      return { passed, failed, skipped: QUALITY_STEPS.slice(), issues };
    }

    const config = await this.deps.readJson(qgPath);
    if (config === null) {
      issues.push("quality-gate.json is invalid JSON. Fix or delete it.");
      return { passed, failed, skipped, issues };
    }

    for (const step of QUALITY_STEPS) {
      const cmd = config[step];
      if (cmd === undefined || cmd === null || typeof cmd !== "string" || !cmd.trim()) {
        skipped.push(step);
        continue;
      }

      const check = isSafeCommand(cmd);
      if (!check.safe) {
        failed.push(step);
        issues.push(`BLOCKED ${step}: '${cmd}' (${check.reason})`);
        continue;
      }

      try {
        const result = await this.deps.runCommand(check.argv, projectDir, 60_000);
        if (result.exitCode === 0) {
          passed.push(step);
        } else {
          failed.push(step);
          const snippet = (result.stderr || result.stdout).slice(0, 300);
          issues.push(`FAIL ${step}: ${cmd} (exit ${result.exitCode})\n${snippet}`);
        }
      } catch {
        failed.push(step);
        issues.push(`TIMEOUT ${step}: ${cmd}`);
      }
    }

    return { passed, failed, skipped, issues };
  }
}

export interface TestIssue {
  readonly category: string;
  readonly message: string;
}

const FAKE_PATTERNS: readonly [RegExp, string][] = [
  [/expect\s*\(\s*true\s*\)\s*\.to(?:Be|Equal)\s*\(\s*true\s*\)/, "assert true === true"],
  [/expect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)/, "assert 1 === 1"],
  [/assert\s+True\b/, "assert True (Python)"],
  [/assert\s+1\s*==\s*1/, "assert 1 == 1"],
];

const TYPE_CHECK_RE = /typeof\s+\w+|instanceof\s+\w+|toBeDefined|toBeInstanceOf|\.type\b/g;
const BEHAVIOR_CHECK_RE =
  /toEqual|toContain|toMatch|toThrow|rejects|resolves|toHaveBeenCalledWith|toHaveProperty|toHaveLength|toBeGreaterThan|toBeLessThan|assert.*==|assertEqual|assertIn|assertRaises|assert_called_with/g;
const ERROR_TESTS_RE =
  /toThrow|rejects|assertRaises|error|invalid|empty|null|undefined|edge.case|boundary|overflow|timeout|unauthorized|forbidden|not.found|bad.request|missing|malformed/i;
const TEST_COUNT_RE = /(test|it|describe)\s*\(/g;
const MOCK_COUNT_RE = /jest\.mock|mock\(|patch\(|MagicMock|stub\(|sinon\.stub/g;
const ASSERTION_COUNT_RE = /\bassert\b|\bexpect\s*\(|\.should\b|\bverify\s*\(/g;

const SKIP_PATTERNS: readonly [RegExp, string][] = [
  [/@pytest\.mark\.skip/, "@pytest.mark.skip"],
  [/@pytest\.mark\.skipIf/, "@pytest.mark.skipIf"],
  [/@unittest\.skip/, "@unittest.skip"],
  [/\bit\.skip\s*\(/, "it.skip()"],
  [/\bdescribe\.skip\s*\(/, "describe.skip()"],
  [/\bxit\s*\(/, "xit()"],
  [/\bxdescribe\s*\(/, "xdescribe()"],
];

export class TddGate {
  analyzeTestContent(content: string, _filename = "test.ts"): TestIssue[] {
    const issues: TestIssue[] = [];

    for (const [pattern, label] of FAKE_PATTERNS) {
      if (pattern.test(content)) {
        issues.push({ category: "FAKE", message: label });
      }
    }

    const typeChecks = (content.match(TYPE_CHECK_RE) ?? []).length;
    const behaviorChecks = (content.match(BEHAVIOR_CHECK_RE) ?? []).length;

    if (typeChecks > 3 && behaviorChecks === 0) {
      issues.push({
        category: "BOILERPLATE",
        message: "Only checks types/existence, never tests actual behavior",
      });
    }

    const hasErrorTests = ERROR_TESTS_RE.test(content);
    const testCount = (content.match(TEST_COUNT_RE) ?? []).length;
    if (testCount >= 3 && !hasErrorTests) {
      issues.push({
        category: "HAPPY_PATH_ONLY",
        message: "No error/edge case tests",
      });
    }

    const mockCount = (content.match(MOCK_COUNT_RE) ?? []).length;
    if (mockCount > 5 && behaviorChecks <= 1) {
      issues.push({
        category: "OVER_MOCKED",
        message: "Heavy mocking but barely tests real behavior",
      });
    }

    for (const [pattern, label] of SKIP_PATTERNS) {
      if (pattern.test(content)) {
        issues.push({
          category: "SKIP",
          message: `${label} — skipped tests hide failures`,
        });
      }
    }

    const assertionCount = (content.match(ASSERTION_COUNT_RE) ?? []).length;
    if (mockCount >= 3 && mockCount <= 5 && assertionCount < mockCount / 2) {
      issues.push({
        category: "MOCK_HEAVY",
        message: `${mockCount} mocks but only ${assertionCount} assertions`,
      });
    }

    return issues;
  }
}

function splitCommand(cmd: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let inSingle = false;
  let inDouble = false;

  for (let i = 0; i < cmd.length; i++) {
    const ch = cmd[i];
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
    } else if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
    } else if (ch === " " && !inSingle && !inDouble) {
      if (current) {
        tokens.push(current);
        current = "";
      }
    } else {
      current += ch;
    }
  }
  if (current) tokens.push(current);
  return tokens;
}
