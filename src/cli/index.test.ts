import { describe, expect, test } from "bun:test";

const BUN_BIN = "/home/claw/.bun/bin/bun";

describe("CLI entrypoint", () => {
  test("--version outputs 2.3.0", () => {
    const result = Bun.spawnSync({
      cmd: [BUN_BIN, "run", "src/cli/index.ts", "--version"],
      cwd: process.cwd(),
      stdout: "pipe",
      stderr: "pipe",
    });

    const stdout = new TextDecoder().decode(result.stdout).trim();
    const stderr = new TextDecoder().decode(result.stderr).trim();

    expect(result.exitCode).toBe(0);
    expect(stderr).toBe("");
    expect(stdout).toBe("2.3.0");
  });
});
