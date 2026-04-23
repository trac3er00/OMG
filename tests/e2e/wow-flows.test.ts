import { describe, expect, it } from "bun:test";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runAdminFlow } from "../../src/wow/flows/admin.js";
import { runBotFlow } from "../../src/wow/flows/bot.js";
import { runLandingFlow } from "../../src/wow/flows/landing.js";
import { runRefactorFlow } from "../../src/wow/flows/refactor.js";
import { runSaasFlow } from "../../src/wow/flows/saas.js";

async function withTempDir(fn: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), "wow-e2e-"));

  try {
    await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function withTempFilePath(
  fn: (filePath: string) => Promise<void>,
): Promise<void> {
  await withTempDir(async (dir) => {
    const filePath = join(dir, "occupied-path");
    await writeFile(filePath, "occupied");
    await fn(filePath);
  });
}

async function expectFileContains(
  filePath: string,
  text: string,
): Promise<void> {
  await access(filePath);
  const content = await readFile(filePath, "utf8");
  expect(content).toContain(text);
}

describe("Wow Flows E2E", () => {
  describe("Landing Flow", () => {
    it("generates landing page files", async () => {
      await withTempDir(async (dir) => {
        const result = await runLandingFlow("make a landing page", dir);

        expect(result.flowName).toBe("landing");
        expect(result.success).toBe(true);
        expect(typeof result.buildTime).toBe("number");
        expect((result.buildTime ?? -1) >= 0).toBe(true);

        await expectFileContains(join(dir, "index.html"), "Landing Page");
        await expectFileContains(
          join(dir, "styles.css"),
          "font-family: sans-serif",
        );
      });
    });

    it("handles invalid output dir gracefully", async () => {
      await withTempFilePath(async (filePath) => {
        const result = await runLandingFlow("make a landing page", filePath);

        expect(result.flowName).toBe("landing");
        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      });
    });
  });

  describe("SaaS Flow", () => {
    it("generates SaaS starter files", async () => {
      await withTempDir(async (dir) => {
        const result = await runSaasFlow("create SaaS starter", dir);

        expect(result.flowName).toBe("saas");
        expect(result.success).toBe(true);

        const pkg = JSON.parse(
          await readFile(join(dir, "package.json"), "utf8"),
        ) as {
          name: string;
          wow: { healthEndpoint: string };
        };

        expect(pkg.name).toBe("saas-starter");
        expect(pkg.wow.healthEndpoint).toBe("/health");
        await expectFileContains(
          join(dir, "src/index.js"),
          "app.post('/auth/login', authRoute)",
        );
        await expectFileContains(
          join(dir, "src/routes/health.js"),
          "status: 'ok'",
        );
        await expectFileContains(
          join(dir, "src/routes/auth.js"),
          "Authentication stub not implemented",
        );
        await expectFileContains(
          join(dir, "src/config/db.js"),
          "client: 'postgres'",
        );
      });
    });

    it("returns an error when output path is already a file", async () => {
      await withTempFilePath(async (filePath) => {
        const result = await runSaasFlow("create SaaS starter", filePath);

        expect(result.flowName).toBe("saas");
        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      });
    });
  });

  describe("Bot Flow", () => {
    it("generates Discord bot", async () => {
      await withTempDir(async (dir) => {
        const result = await runBotFlow("create Discord bot", dir);

        expect(result.flowName).toBe("bot");
        expect(result.success).toBe(true);

        const pkg = JSON.parse(
          await readFile(join(dir, "package.json"), "utf8"),
        ) as {
          name: string;
          dependencies: Record<string, string>;
        };

        expect(pkg.name).toBe("discord-bot");
        expect(pkg.dependencies["discord.js"]).toBeDefined();
        await expectFileContains(
          join(dir, "index.js"),
          "GatewayIntentBits.Guilds",
        );
        await expectFileContains(
          join(dir, ".env.example"),
          "BOT_TOKEN=your_token_here",
        );
      });
    });

    it("generates Telegram bot", async () => {
      await withTempDir(async (dir) => {
        const result = await runBotFlow("create Telegram bot", dir);

        expect(result.flowName).toBe("bot");
        expect(result.success).toBe(true);

        const pkg = JSON.parse(
          await readFile(join(dir, "package.json"), "utf8"),
        ) as {
          name: string;
          dependencies: Record<string, string>;
        };

        expect(pkg.name).toBe("telegram-bot");
        expect(pkg.dependencies["node-telegram-bot-api"]).toBeDefined();
        await expectFileContains(join(dir, "index.js"), "polling: true");
      });
    });

    it("returns an error when the bot output path is not a directory", async () => {
      await withTempFilePath(async (filePath) => {
        const result = await runBotFlow("create Discord bot", filePath);

        expect(result.flowName).toBe("bot");
        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      });
    });
  });

  describe("Admin Flow", () => {
    it("generates admin dashboard", async () => {
      await withTempDir(async (dir) => {
        const result = await runAdminFlow("create admin dashboard", dir);

        expect(result.flowName).toBe("admin");
        expect(result.success).toBe(true);

        const pkg = JSON.parse(
          await readFile(join(dir, "package.json"), "utf8"),
        ) as {
          dependencies: Record<string, string>;
        };

        expect(pkg.dependencies.react).toBeDefined();
        expect(pkg.dependencies["react-dom"]).toBeDefined();
        expect(pkg.dependencies["react-scripts"]).toBe("5.0.1");
        await expectFileContains(join(dir, "src/App.jsx"), "Admin Dashboard");
        await expectFileContains(
          join(dir, "src/components/DataTable.jsx"),
          "<th>Status</th>",
        );
        await expectFileContains(
          join(dir, "src/index.jsx"),
          "ReactDOM.createRoot",
        );
      });
    });

    it("returns an error when admin output path is already a file", async () => {
      await withTempFilePath(async (filePath) => {
        const result = await runAdminFlow("create admin dashboard", filePath);

        expect(result.flowName).toBe("admin");
        expect(result.success).toBe(false);
        expect(result.error).toBeDefined();
      });
    });
  });

  describe("Refactor Flow", () => {
    it("analyzes repo without modifying files", async () => {
      await withTempDir(async (dir) => {
        const srcDir = join(dir, "src");
        await mkdir(srcDir, { recursive: true });
        await writeFile(join(dir, "camelCase.ts"), "export const value = 1;\n");
        await writeFile(
          join(dir, "snake_case.ts"),
          "export const value = 2;\n",
        );
        await writeFile(join(dir, "README.md"), "# Temp Repo\n");
        await writeFile(
          join(srcDir, "index.ts"),
          "export const main = true;\n",
        );

        const beforeIndex = await readFile(join(srcDir, "index.ts"), "utf8");
        const result = await runRefactorFlow("refactor this repo", dir);
        const afterIndex = await readFile(join(srcDir, "index.ts"), "utf8");

        expect(result.flowName).toBe("refactor");
        expect(result.success).toBe(true);
        expect(Array.isArray(result.suggestions)).toBe(true);
        expect(result.filesAnalyzed).toBeGreaterThan(0);
        expect(
          result.suggestions.some((suggestion) => suggestion.type === "naming"),
        ).toBe(true);
        expect(result.diffPreview.length).toBe(result.suggestions.length);
        expect(afterIndex).toBe(beforeIndex);
      });
    });

    it("handles missing repos gracefully", async () => {
      const missingRepoDir = join(tmpdir(), `wow-missing-${Date.now()}`);
      const result = await runRefactorFlow(
        "refactor this repo",
        missingRepoDir,
      );

      expect(result.flowName).toBe("refactor");
      expect(result.success).toBe(true);
      expect(result.filesAnalyzed).toBe(0);
      expect(result.suggestions).toEqual([]);
      expect(result.diffPreview).toEqual([]);
    });
  });
});
