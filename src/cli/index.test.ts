import { describe, expect, test } from "bun:test";
import { statSync } from "node:fs";

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
  test("--version outputs 2.5.0", () => {
    const result = runCli("--version");

    const stdout = decode(result.stdout);
    const stderr = decode(result.stderr);

    expect(result.exitCode).toBe(0);
    expect(stderr).toBe("");
    expect(stdout).toBe("2.5.0");
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
    expect(combined).toContain("Unknown argument: nonexistent-command");
  });
});
