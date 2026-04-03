import { describe, expect, test } from "bun:test";

describe("validate command", () => {
  test("returns structured json report", () => {
    const result = Bun.spawnSync({
      cmd: ["bun", "run", "src/cli/index.ts", "validate", "--json"],
      cwd: process.cwd(),
      stdout: "pipe",
      stderr: "pipe",
    });

    const stdout = new TextDecoder().decode(result.stdout).trim();
    expect(stdout.length).toBeGreaterThan(0);

    const payload = JSON.parse(stdout) as {
      status: "pass" | "fail";
      checks: Array<{ name: string; status: "pass" | "fail" | "skip" }>;
    };

    expect(["pass", "fail"]).toContain(payload.status);
    expect(payload.checks.length).toBeGreaterThanOrEqual(3);
    expect(payload.checks.map((check) => check.name)).toContain(
      "host-config-files",
    );
    expect(payload.checks.map((check) => check.name)).toContain(
      "skills-directories",
    );
    expect(payload.checks.map((check) => check.name)).toContain(
      "compensators-test-suite",
    );
  });
});
