import { describe, expect, test } from "bun:test";
import {
  configureVision,
  extractText,
  resetVisionConfiguration,
  VisionNotSupportedError,
} from "../vision/index.js";
import type { HostType } from "../types/config.js";
import {
  checkParity,
  checkStreamParity,
  type ProviderResponse,
  type ProviderStreamEvent,
} from "./parity.js";

const PARITY_PROMPT = "Normalize this provider response.";

const PROVIDER_MODELS: Record<HostType, string> = {
  claude: "claude-sonnet-4",
  codex: "gpt-5-codex",
  gemini: "gemini-2.5-pro",
  kimi: "kimi-k2",
  ollama: "llama3:latest",
  "ollama-cloud": "llama3:latest",
  opencode: "opencode-compatible",
};

const PROVIDER_TOKENS: Record<
  HostType,
  { inputTokens: number; outputTokens: number }
> = {
  claude: { inputTokens: 18, outputTokens: 9 },
  codex: { inputTokens: 19, outputTokens: 9 },
  gemini: { inputTokens: 17, outputTokens: 10 },
  kimi: { inputTokens: 18, outputTokens: 10 },
  ollama: { inputTokens: 20, outputTokens: 11 },
  "ollama-cloud": { inputTokens: 20, outputTokens: 11 },
  opencode: { inputTokens: 18, outputTokens: 9 },
};

function mockResponse(provider: HostType, prompt: string): ProviderResponse {
  return {
    content: `Normalized reply for: ${prompt}`,
    model: PROVIDER_MODELS[provider],
    usage: PROVIDER_TOKENS[provider],
    provider,
  };
}

function mockStream(provider: HostType): ProviderStreamEvent[] {
  return [
    {
      provider,
      model: PROVIDER_MODELS[provider],
      type: "start",
    },
    {
      provider,
      model: PROVIDER_MODELS[provider],
      type: "content",
      content: "Normalized ",
    },
    {
      provider,
      model: PROVIDER_MODELS[provider],
      type: "content",
      content: "reply",
    },
    {
      provider,
      model: PROVIDER_MODELS[provider],
      type: "done",
      usage: PROVIDER_TOKENS[provider],
    },
  ];
}

describe("provider parity synthetic contract tests", () => {
  test("synthetic responses satisfy normalized format across all 7 providers", () => {
    const providers: HostType[] = [
      "claude",
      "codex",
      "gemini",
      "kimi",
      "ollama",
      "ollama-cloud",
      "opencode",
    ];
    const responses = providers.map((provider) =>
      mockResponse(provider, PARITY_PROMPT),
    );

    for (const response of responses) {
      expect(response).toEqual({
        content: expect.any(String),
        model: expect.any(String),
        usage: {
          inputTokens: expect.any(Number),
          outputTokens: expect.any(Number),
        },
        provider: expect.any(String),
      });
    }

    const report = checkParity(responses);
    expect(report.isFormatConsistent).toBe(true);
    expect(report.providersSeen).toHaveLength(7);
    expect(report.missingProviders).toHaveLength(0);
    expect(report.variance.map((entry) => entry.field)).toEqual([
      "model",
      "usage.inputTokens",
      "usage.outputTokens",
    ]);
  });

  test("synthetic parity check reports content drift as acceptable variance instead of format failure", () => {
    const responses: ProviderResponse[] = [
      mockResponse("claude", PARITY_PROMPT),
      mockResponse("codex", PARITY_PROMPT),
      mockResponse("gemini", PARITY_PROMPT),
      mockResponse("kimi", `${PARITY_PROMPT} (alternate wording)`),
      mockResponse("ollama", PARITY_PROMPT),
      mockResponse("ollama-cloud", PARITY_PROMPT),
      mockResponse("opencode", PARITY_PROMPT),
    ];

    const report = checkParity(responses);
    expect(report.isFormatConsistent).toBe(true);
    expect(report.variance.find((entry) => entry.field === "content")).toEqual({
      field: "content",
      baseline: "Normalized reply for: Normalize this provider response.",
      mismatches: [
        {
          provider: "kimi",
          value:
            "Normalized reply for: Normalize this provider response. (alternate wording)",
        },
      ],
    });
  });

  test("provider without vision support throws VisionNotSupportedError", async () => {
    configureVision({ provider: "codex" });
    try {
      await expect(extractText("/tmp/does-not-matter.png")).rejects.toThrow(
        VisionNotSupportedError,
      );
    } finally {
      resetVisionConfiguration();
    }
  });

  test("synthetic stream events use a consistent normalized format", () => {
    const providers: HostType[] = [
      "claude",
      "codex",
      "gemini",
      "kimi",
      "ollama",
      "ollama-cloud",
      "opencode",
    ];
    const events = providers.flatMap((provider) => mockStream(provider));

    const report = checkStreamParity(events);
    expect(report.isConsistent).toBe(true);
    expect(report.formatInconsistencies).toHaveLength(0);
    expect(report.sequenceByProvider.claude).toEqual([
      "start",
      "content",
      "content",
      "done",
    ]);
    expect(report.sequenceByProvider.ollama).toEqual([
      "start",
      "content",
      "content",
      "done",
    ]);
  });
});
