import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { deploy, detectDeployTarget } from "./integrations.js";

function createTempProject(files: Record<string, string> = {}): string {
  const dir = mkdtempSync(join(tmpdir(), "omg-deploy-"));
  for (const [name, contents] of Object.entries(files)) {
    writeFileSync(join(dir, name), contents, "utf8");
  }
  return dir;
}

describe("deploy integrations", () => {
  test("detects vercel from marker file", () => {
    const dir = createTempProject({ "vercel.json": "{}" });

    try {
      expect(detectDeployTarget(dir)).toBe("vercel");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("detects netlify from marker file", () => {
    const dir = createTempProject({ "netlify.toml": "[build]\n" });

    try {
      expect(detectDeployTarget(dir)).toBe("netlify");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("defaults to railway when no marker exists", () => {
    const dir = createTempProject();

    try {
      expect(detectDeployTarget(dir)).toBe("railway");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("dry run reports detected target and command", async () => {
    const dir = createTempProject({ "fly.toml": 'app = "demo"\n' });

    try {
      const result = await deploy(detectDeployTarget(dir), dir, true);

      expect(result.success).toBe(true);
      expect(result.message).toContain("fly");
      expect(result.message).toContain(
        "would execute fly deploy --remote-only",
      );
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
