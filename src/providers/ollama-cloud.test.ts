import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { ModelTier } from "../orchestration/router.js";
import { OllamaCloudProvider } from "./ollama-cloud.js";

const API_KEY_ENV = "OLLAMA_API_KEY";

let originalFetch: typeof globalThis.fetch;
let originalApiKey: string | undefined;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  originalApiKey = process.env[API_KEY_ENV];
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalApiKey === undefined) {
    delete process.env[API_KEY_ENV];
    return;
  }
  process.env[API_KEY_ENV] = originalApiKey;
});

describe("OllamaCloudProvider.healthCheck", () => {
  test("mock fetch returns healthy status with bearer auth", async () => {
    process.env[API_KEY_ENV] = "test-api-key";
    let capturedInit: RequestInit | undefined;
    let capturedUrl: RequestInfo | URL | undefined;

    globalThis.fetch = mock((input: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = input;
      capturedInit = init;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            models: [
              {
                name: "llama3.1:8b",
                size: 8_000_000_000,
                digest: "abc123",
                modified_at: "2026-04-21T00:00:00Z",
              },
            ],
          }),
          { status: 200 },
        ),
      );
    }) as unknown as typeof fetch;

    const provider = new OllamaCloudProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(true);
    expect(status.authOk).toBe(true);
    expect(status.liveConnection).toBe(true);
    expect(status.statusMessage).toContain("1 model(s) available");

    expect(String(capturedUrl)).toBe("https://ollama.com/api/tags");
    const headers = new Headers(capturedInit?.headers);
    expect(headers.get("Authorization")).toBe("Bearer test-api-key");
  });
});

describe("OllamaCloudProvider.isAvailable", () => {
  test("returns false when OLLAMA_API_KEY is not set", async () => {
    delete process.env[API_KEY_ENV];
    const provider = new OllamaCloudProvider();
    expect(await provider.isAvailable()).toBe(false);
  });
});

describe("OllamaCloudProvider.getMcpConfig", () => {
  test("returns valid MCP config structure", () => {
    const provider = new OllamaCloudProvider();
    const config = provider.getMcpConfig("npx", ["@trac3r/oh-my-god"]);

    expect(config).toEqual({
      mcpServers: {
        "omg-control": {
          command: "npx",
          args: ["@trac3r/oh-my-god"],
        },
      },
    });
  });
});

describe("OllamaCloudProvider.inferTier", () => {
  test("maps model names to expected tiers", () => {
    expect(OllamaCloudProvider.inferTier("llama3.1:8b")).toBe(ModelTier.Haiku);
    expect(OllamaCloudProvider.inferTier("llama3.3:70b")).toBe(
      ModelTier.Sonnet,
    );
    expect(OllamaCloudProvider.inferTier("qwen3:235b")).toBe(ModelTier.Opus);
    expect(OllamaCloudProvider.inferTier("mixtral:8x22b")).toBe(ModelTier.Opus);
  });
});
