import { describe, expect, mock, test } from "bun:test";
import { tryWowFlow } from "./instant.js";

const mockLandingResult = {
  flowName: "landing",
  success: true,
  proofScore: 75,
  buildTime: 100,
  url: "https://example.com/landing",
};

const mockSaasResult = {
  flowName: "saas",
  success: true,
  proofScore: 65,
  buildTime: 200,
};

const mockBotResult = {
  flowName: "bot",
  success: true,
  proofScore: 65,
  buildTime: 150,
};

const mockAdminResult = {
  flowName: "admin",
  success: true,
  proofScore: 70,
  buildTime: 180,
};

const mockRefactorResult = {
  flowName: "refactor",
  success: true,
  proofScore: 60,
  buildTime: 250,
  suggestions: [],
  filesAnalyzed: 10,
  diffPreview: [],
};

mock.module("../../wow/flows/landing.js", () => ({
  runLandingFlow: mock(() => Promise.resolve(mockLandingResult)),
}));

mock.module("../../wow/flows/saas.js", () => ({
  runSaasFlow: mock(() => Promise.resolve(mockSaasResult)),
}));

mock.module("../../wow/flows/bot.js", () => ({
  runBotFlow: mock(() => Promise.resolve(mockBotResult)),
}));

mock.module("../../wow/flows/admin.js", () => ({
  runAdminFlow: mock(() => Promise.resolve(mockAdminResult)),
}));

mock.module("../../wow/flows/refactor.js", () => ({
  runRefactorFlow: mock(() => Promise.resolve(mockRefactorResult)),
}));

describe("tryWowFlow", () => {
  const targetDir = "/tmp/test-output";

  test("landing page prompt triggers landing flow", async () => {
    const result = await tryWowFlow("make a landing page", targetDir);

    expect(result).not.toBeNull();
    expect(result?.type).toBe("landing");
    expect(result?.success).toBe(true);
    expect(result?.proofScore).toBe(75);
    expect(result?.target_dir).toBe(targetDir);
  });

  test("saas prompt triggers saas flow", async () => {
    const result = await tryWowFlow("build a SaaS app", targetDir);

    expect(result).not.toBeNull();
    expect(result?.type).toBe("saas");
    expect(result?.success).toBe(true);
    expect(result?.proofScore).toBe(65);
  });

  test("unknown prompt returns null from tryWowFlow", async () => {
    const result = await tryWowFlow("create a weather app", targetDir);

    expect(result).toBeNull();
  });

  test("all 5 flow keywords are recognized", async () => {
    const testCases = [
      { prompt: "landing", expectedType: "landing" },
      { prompt: "saas starter kit", expectedType: "saas" },
      { prompt: "discord bot", expectedType: "bot" },
      { prompt: "telegram bot", expectedType: "bot" },
      { prompt: "admin panel", expectedType: "admin" },
      { prompt: "admin dashboard", expectedType: "admin" },
      { prompt: "refactor the auth module", expectedType: "refactor" },
    ];

    for (const { prompt, expectedType } of testCases) {
      const result = await tryWowFlow(prompt, targetDir);
      expect(result).not.toBeNull();
      expect(result?.type).toBe(expectedType);
    }
  });

  test("tryWowFlow returns InstantPayload shape on success", async () => {
    const result = await tryWowFlow("landing page for my startup", targetDir);

    expect(result).not.toBeNull();
    expect(result).toHaveProperty("success");
    expect(result).toHaveProperty("type");
    expect(result).toHaveProperty("target_dir");
    expect(result).toHaveProperty("file_count");
    expect(result).toHaveProperty("proofScore");

    expect(typeof result?.success).toBe("boolean");
    expect(typeof result?.type).toBe("string");
    expect(typeof result?.target_dir).toBe("string");
    expect(typeof result?.file_count).toBe("number");
  });

  test("bot flow detects telegram vs discord from prompt", async () => {
    const discordResult = await tryWowFlow("create a discord bot", targetDir);
    expect(discordResult?.type).toBe("bot");

    const telegramResult = await tryWowFlow("build telegram bot", targetDir);
    expect(telegramResult?.type).toBe("bot");
  });

  test("case-insensitive matching works", async () => {
    const results = await Promise.all([
      tryWowFlow("LANDING PAGE", targetDir),
      tryWowFlow("Build a SAAS", targetDir),
      tryWowFlow("ADMIN Dashboard", targetDir),
      tryWowFlow("REFACTOR code", targetDir),
    ]);

    expect(results[0]?.type).toBe("landing");
    expect(results[1]?.type).toBe("saas");
    expect(results[2]?.type).toBe("admin");
    expect(results[3]?.type).toBe("refactor");
  });

  test("dry-run skips flow execution and returns preview payload", async () => {
    const result = await tryWowFlow("make a landing page", targetDir, {
      dryRun: true,
    });

    expect(result).not.toBeNull();
    expect(result?.type).toBe("landing");
    expect(result?.success).toBe(true);
    expect(result?.dry_run).toBe(true);
    expect(result?.target_dir).toBe(targetDir);
    expect(result?.file_count).toBe(0);
    expect(result?.url).toBeUndefined();
    expect(result?.proofScore).toBeUndefined();
    expect(String(result?.warning ?? "")).toContain("[dry-run]");
  });

  test("dry-run preview is non-mutating across all 5 flow types", async () => {
    const flows: ReadonlyArray<{ prompt: string; expectedType: string }> = [
      { prompt: "landing page", expectedType: "landing" },
      { prompt: "build a saas", expectedType: "saas" },
      { prompt: "discord bot", expectedType: "bot" },
      { prompt: "admin panel", expectedType: "admin" },
      { prompt: "refactor auth", expectedType: "refactor" },
    ];
    for (const { prompt, expectedType } of flows) {
      const result = await tryWowFlow(prompt, targetDir, { dryRun: true });
      expect(result?.dry_run).toBe(true);
      expect(result?.type).toBe(expectedType);
      expect(result?.url).toBeUndefined();
    }
  });
});
