import { expect, test, describe } from "bun:test";
import { runBotFlow } from "./bot.js";
import { readFile, stat } from "node:fs/promises";
import { join } from "node:path";

describe("Bot Flow", () => {
  test("creates Discord bot scaffolding", async () => {
    const outputDir =
      "/tmp/test-discord-" + Math.random().toString(36).slice(2);
    const result = await runBotFlow("create Discord bot", outputDir);

    expect(result.flowName).toBe("bot");
    expect(result.success).toBe(true);
    expect(result.buildTime).toBeGreaterThan(0);
    expect(result.proofScore).toBe(65);

    const pkgContent = await readFile(join(outputDir, "package.json"), "utf-8");
    const pkg = JSON.parse(pkgContent);
    expect(pkg.name).toBe("discord-bot");
    expect(pkg.dependencies["discord.js"]).toBeDefined();

    const indexStat = await stat(join(outputDir, "index.js"));
    expect(indexStat.isFile()).toBe(true);

    const envContent = await readFile(join(outputDir, ".env.example"), "utf-8");
    expect(envContent).toContain("BOT_TOKEN");
  });

  test("creates Telegram bot scaffolding", async () => {
    const outputDir =
      "/tmp/test-telegram-" + Math.random().toString(36).slice(2);
    const result = await runBotFlow("create Telegram bot", outputDir);

    expect(result.flowName).toBe("bot");
    expect(result.success).toBe(true);
    expect(result.buildTime).toBeGreaterThan(0);
    expect(result.proofScore).toBe(65);

    const pkgContent = await readFile(join(outputDir, "package.json"), "utf-8");
    const pkg = JSON.parse(pkgContent);
    expect(pkg.name).toBe("telegram-bot");
    expect(pkg.dependencies["node-telegram-bot-api"]).toBeDefined();

    const indexContent = await readFile(join(outputDir, "index.js"), "utf-8");
    expect(indexContent).toContain("TelegramBot");

    const envContent = await readFile(join(outputDir, ".env.example"), "utf-8");
    expect(envContent).toContain("BOT_TOKEN");
  });

  test("defaults to Discord when platform not specified", async () => {
    const outputDir =
      "/tmp/test-default-bot-" + Math.random().toString(36).slice(2);
    const result = await runBotFlow("create a chat bot", outputDir);

    expect(result.success).toBe(true);
    const pkgContent = await readFile(join(outputDir, "package.json"), "utf-8");
    const pkg = JSON.parse(pkgContent);
    expect(pkg.name).toBe("discord-bot");
  });

  test("graceful failure when outputDir is invalid", async () => {
    const result = await runBotFlow("create Discord bot", "/dev/null/invalid");

    expect(result.flowName).toBe("bot");
    expect(result.success).toBe(false);
    expect(result.error).toBeDefined();
  });
});
