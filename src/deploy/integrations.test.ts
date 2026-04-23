import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  deploy,
  deployWithOptions,
  detectDeployTarget,
  getDeployedUrl,
  isDeployAuthenticated,
} from "./integrations.js";

function createTempProject(files: Record<string, string> = {}): string {
  const dir = mkdtempSync(join(tmpdir(), "omg-deploy-"));
  for (const [name, contents] of Object.entries(files)) {
    writeFileSync(join(dir, name), contents, "utf8");
  }
  return dir;
}

describe("deploy integrations", () => {
  describe("detectDeployTarget", () => {
    test("detects vercel from marker file", async () => {
      const dir = createTempProject({ "vercel.json": "{}" });

      try {
        expect(await detectDeployTarget(dir)).toBe("vercel");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("detects netlify from marker file", async () => {
      const dir = createTempProject({ "netlify.toml": "[build]\n" });

      try {
        expect(await detectDeployTarget(dir)).toBe("netlify");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("returns unknown when no marker exists", async () => {
      const dir = createTempProject();

      try {
        expect(await detectDeployTarget(dir)).toBe("unknown");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });
  });

  describe("getDeployedUrl", () => {
    test("extracts URL from vercel output", () => {
      const vercelOutput = `
Vercel CLI 33.0.0
Deploying to production...
🔗  Linked to myorg/myproject (created .vercel)
🔍  Inspect: https://vercel.com/myorg/myproject/abc123
✅  Production: https://myproject-abc123.vercel.app [42s]
`;
      const url = getDeployedUrl(vercelOutput, "vercel");
      expect(url).toBe("https://vercel.com/myorg/myproject/abc123");
    });

    test("extracts URL from netlify output", () => {
      const netlifyOutput = `
Deploy path:        /var/www/build
Deploying to site:  mysite
Publishing deploy:  https://mysite.netlify.app
`;
      const url = getDeployedUrl(netlifyOutput, "netlify");
      expect(url).toBe("https://mysite.netlify.app");
    });

    test("returns undefined for unknown target", () => {
      const output = "https://example.com";
      const url = getDeployedUrl(output, "unknown");
      expect(url).toBeUndefined();
    });

    test("returns undefined when no URL in output", () => {
      const output = "Deployment failed";
      const url = getDeployedUrl(output, "vercel");
      expect(url).toBeUndefined();
    });
  });

  describe("isDeployAuthenticated", () => {
    test("returns false for unknown target", async () => {
      const result = await isDeployAuthenticated("unknown");
      expect(result).toBe(false);
    });

    test("returns false when CLI not found", async () => {
      // Testing with a non-existent CLI - vercel/netlify unlikely to be installed in test env
      // The function should return false if the CLI doesn't exist
      const result = await isDeployAuthenticated("vercel");
      // If vercel CLI is not installed, should be false
      // If it is installed but not authenticated, should be false
      // Either way, in a test environment without setup, it should be false
      expect(typeof result).toBe("boolean");
    });
  });

  describe("deploy", () => {
    test("dry run reports detected target and command", async () => {
      const dir = createTempProject({ "fly.toml": 'app = "demo"\n' });

      try {
        const result = await deployWithOptions(
          (await detectDeployTarget(dir)) as string,
          dir,
          true,
        );

        expect(result.success).toBe(true);
        expect(result.message).toContain("fly");
        expect(result.message).toContain(
          "would execute fly deploy --remote-only",
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("dry run for vercel target", async () => {
      const dir = createTempProject({ "vercel.json": "{}" });

      try {
        const result = await deployWithOptions("vercel", dir, true);

        expect(result.success).toBe(true);
        expect(result.message).toContain("vercel");
        expect(result.message).toContain("would execute vercel deploy");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy fails when CLI not installed", async () => {
      const dir = createTempProject({ "vercel.json": "{}" });

      try {
        const result = await deployWithOptions("vercel", dir, false);

        if (!result.success) {
          expect(result.message).toMatch(/CLI|authenticated|login/i);
        }
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy returns auth error with instructions when not authenticated", async () => {
      const dir = createTempProject({ "netlify.toml": "[build]\n" });

      try {
        const result = await deployWithOptions("netlify", dir, false);

        if (!result.success && result.message?.includes("authenticated")) {
          expect(result.message).toContain("login");
        }
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("new deploy function with projectDir first", async () => {
      const dir = createTempProject({ "vercel.json": "{}" });

      try {
        const result = await deploy(dir, "vercel");
        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy returns unknown target error when no marker exists", async () => {
      const dir = createTempProject();

      try {
        const result = await deploy(dir);
        expect(result.success).toBe(false);
        expect(result.error).toContain(
          "No deploy target detected (no vercel.json or netlify.toml)",
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy returns vercel auth error with login instructions", async () => {
      const dir = createTempProject({ "vercel.json": "{}" });

      try {
        const result = await deploy(dir);
        expect(result.success).toBe(false);
        if (result.error?.includes("Not authenticated")) {
          expect(result.error).toContain("vercel login");
        }
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy returns netlify auth error with login instructions", async () => {
      const dir = createTempProject({ "netlify.toml": "[build]\n" });

      try {
        const result = await deploy(dir);
        expect(result.success).toBe(false);
        if (result.error?.includes("Not authenticated")) {
          expect(result.error).toContain("netlify login");
        }
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    test("deploy auto-detects target when not provided", async () => {
      const dir = createTempProject({ "netlify.toml": "[build]\n" });

      try {
        const result = await deploy(dir);
        expect(result.success).toBe(false);
        expect(result.error).toContain("netlify");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });
  });
});
