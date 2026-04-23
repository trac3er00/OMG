import { describe, expect, test } from "bun:test";
import { statSync } from "node:fs";

import { CLI_VERSION } from "./index.js";

const BUN_BIN = process.execPath;

function runCli(...args: string[]) {
  return Bun.spawnSync({
    cmd: [BUN_BIN, "run", "src/cli/index.ts", ...args],
    cwd: process.cwd(),
    stdout: "pipe",
    stderr: "pipe",
  });
}

function decode(buffer: Uint8Array): string {
  return new TextDecoder().decode(buffer).trim();
}

describe("CLI entrypoint", () => {
  test("CLI_VERSION constant is 2.6.0", () => {
    expect(CLI_VERSION).toBe("2.6.0");
  });

  test("--version outputs 2.6.0", () => {
    const result = runCli("--version");

    const stdout = decode(result.stdout);
    const stderr = decode(result.stderr);

    expect(result.exitCode).toBe(0);
    expect(stderr).toBe("");
    expect(stdout).toBe("2.6.0");
  });

  test("entrypoint is executable for npx bin resolution", () => {
    const mode = statSync("src/cli/index.ts").mode;

    expect(mode & 0o111).not.toBe(0);
  });

  test("--help lists primary commands", () => {
    const result = runCli("--help");
    const stdout = decode(result.stdout);

    expect(result.exitCode).toBe(0);
    expect(stdout).toContain("omg env doctor");
    expect(stdout).toContain("omg init");
    expect(stdout).toContain("omg validate");
  });

  test("env doctor --json returns structured checks", () => {
    const result = runCli("env", "doctor", "--json");
    const stdout = decode(result.stdout);

    expect(result.exitCode).toBe(0);

    const payload = JSON.parse(stdout) as {
      checks: Array<{ name: string; status: "found" | "missing" }>;
    };

    expect(payload.checks.length).toBeGreaterThanOrEqual(4);
    expect(payload.checks.map((check) => check.name)).toContain("bun");
    expect(payload.checks.map((check) => check.name)).toContain("git");
  });

  test("unknown commands fail with a clear error", () => {
    const result = runCli("nonexistent-command");
    const combined = [decode(result.stdout), decode(result.stderr)]
      .filter(Boolean)
      .join("\n");

    expect(result.exitCode).toBe(1);
    expect(combined).toContain("Unknown command or goal");
  });

  test("goal as first arg without subcommand with --dry-run outputs classification JSON", () => {
    const result = runCli("make landing page", "--dry-run");
    const stdout = decode(result.stdout);
    const stderr = decode(result.stderr);

    expect(result.exitCode).toBe(0);
    expect(stderr).toBe("");

    const payload = JSON.parse(stdout) as {
      goal: string;
      classified: boolean;
      intent: string;
      risk: string;
      complexity: string;
      confidence: number;
    };

    expect(payload).toEqual({
      goal: "make landing page",
      classified: true,
      intent: "build",
      risk: "low",
      complexity: "simple",
      confidence: 0.9,
    });
  });

  test("high-risk dry-run goals print warning and classified payload", () => {
    const result = runCli("delete all data", "--dry-run");
    const stdout = decode(result.stdout);
    const stderr = decode(result.stderr);

    expect(result.exitCode).toBe(0);
    expect(stderr).toContain(
      '⚠️  Risk warning: critical risk detected for goal: "delete all data"',
    );

    const payload = JSON.parse(stdout) as {
      goal: string;
      classified: boolean;
      intent: string;
      risk: string;
      complexity: string;
      confidence: number;
    };

    expect(payload.goal).toBe("delete all data");
    expect(payload.classified).toBe(true);
    expect(payload.intent).toBe("modify");
    expect(payload.risk).toBe("critical");
    expect(payload.complexity).toBe("expert");
    expect(payload.confidence).toBe(0.9);
  });

  test("non-simple goals without --dry-run print classification guidance", () => {
    const result = runCli("deploy production api");
    const stdout = decode(result.stdout);
    const stderr = decode(result.stderr);

    expect(result.exitCode).toBe(0);
    expect(stderr).toContain(
      '⚠️  Risk warning: high risk detected for goal: "deploy production api"',
    );
    expect(stdout).toContain(
      "Goal classified as: deploy / high risk / moderate",
    );
    expect(stdout).toContain(
      'Suggested: omg instant "deploy production api" for build tasks, or omg deep-plan for complex tasks',
    );
  });

  test("instant command still works as backward compatible", () => {
    const result = runCli("instant", "build a landing page");
    const combined = [decode(result.stdout), decode(result.stderr)]
      .filter(Boolean)
      .join("\n");

    expect(combined).not.toContain("Unknown argument");
    expect(combined).not.toContain("Unknown command or goal");
  });
});
