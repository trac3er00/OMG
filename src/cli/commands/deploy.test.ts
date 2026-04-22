import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ROOT = process.cwd();
const BUN_BIN = "/home/claw/.bun/bin/bun";

describe("deploy command", () => {
  test("dry run reports detected provider", () => {
    const projectDir = mkdtempSync(join(tmpdir(), "omg-cli-deploy-"));
    writeFileSync(join(projectDir, "vercel.json"), "{}\n", "utf8");

    try {
      const result = Bun.spawnSync({
        cmd: [
          BUN_BIN,
          "run",
          join(ROOT, "src/cli/index.ts"),
          "deploy",
          "--dry-run",
          "--json",
          "--project-dir",
          projectDir,
        ],
        cwd: ROOT,
        stdout: "pipe",
        stderr: "pipe",
      });

      expect(result.exitCode).toBe(0);

      const stdout = new TextDecoder().decode(result.stdout).trim();
      const payload = JSON.parse(stdout) as {
        success: boolean;
        target: string;
        dryRun: boolean;
        message: string;
      };

      expect(payload.success).toBe(true);
      expect(payload.target).toBe("vercel");
      expect(payload.dryRun).toBe(true);
      expect(payload.message).toContain("Detected vercel deployment target");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});
