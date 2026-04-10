import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { ModelTier } from "../orchestration/router.js";
import { OllamaProvider } from "./ollama.js";

const MOCK_MODELS_RESPONSE = {
  models: [
    {
      name: "llama3:latest",
      size: 4_661_211_168,
      digest: "abc123",
      modified_at: "2024-01-01T00:00:00Z",
    },
    {
      name: "codellama:70b",
      size: 38_000_000_000,
      digest: "def456",
      modified_at: "2024-01-02T00:00:00Z",
    },
  ],
};

const MOCK_CHAT_RESPONSE = {
  model: "llama3:latest",
  message: { role: "assistant", content: "Hello! How can I help you?" },
  done: true,
  eval_count: 42,
};

let originalFetch: typeof globalThis.fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("OllamaProvider", () => {
  test("hostType is ollama", () => {
    const provider = new OllamaProvider();
    expect(provider.hostType).toBe("ollama");
  });

  test("surface matches ollama host", () => {
    const provider = new OllamaProvider();
    expect(provider.surface.hostType).toBe("ollama");
    expect(provider.surface.cliCommand).toBe("ollama");
    expect(provider.surface.transportType).toBe("http-sse");
    expect(provider.surface.supportsHooks).toBe(false);
  });

  test("default baseUrl is localhost:11434", () => {
    const provider = new OllamaProvider();
    expect(provider.baseUrl).toBe("http://localhost:11434");
  });

  test("custom baseUrl is respected", () => {
    const provider = new OllamaProvider("http://remote:8080");
    expect(provider.baseUrl).toBe("http://remote:8080");
  });

  test("getMcpConfig returns mcpServers format", () => {
    const provider = new OllamaProvider();
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

describe("OllamaProvider.healthCheck", () => {
  test("mock 200 with model list returns healthy status", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(MOCK_MODELS_RESPONSE), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(true);
    expect(status.authOk).toBe(true);
    expect(status.liveConnection).toBe(true);
    expect(status.statusMessage).toContain("2 model(s) available");
  });

  test("mock 200 with empty model list returns healthy status", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify({ models: [] }), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(true);
    expect(status.authOk).toBe(true);
    expect(status.liveConnection).toBe(true);
    expect(status.statusMessage).toContain("0 model(s) available");
  });

  test("mock connection refused returns graceful error", async () => {
    globalThis.fetch = mock(() =>
      Promise.reject(new TypeError("fetch failed")),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(false);
    expect(status.authOk).toBe(false);
    expect(status.liveConnection).toBe(false);
    expect(status.statusMessage).toContain("not reachable");
    expect(status.installHint).toContain("ollama serve");
  });

  test("mock ECONNREFUSED returns graceful error", async () => {
    globalThis.fetch = mock(() =>
      Promise.reject(new Error("connect ECONNREFUSED 127.0.0.1:11434")),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(false);
    expect(status.authOk).toBe(false);
    expect(status.liveConnection).toBe(false);
    expect(status.statusMessage).toContain("not reachable");
  });

  test("mock non-connection error returns graceful error with message", async () => {
    globalThis.fetch = mock(() =>
      Promise.reject(new Error("DNS resolution failed")),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const status = await provider.healthCheck();

    expect(status.available).toBe(false);
    expect(status.statusMessage).toContain("DNS resolution failed");
    expect(status.installHint).toBeDefined();
  });
});

describe("OllamaProvider.chat", () => {
  test("mock chat request returns normalized response", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(MOCK_CHAT_RESPONSE), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const response = await provider.chat({
      model: "llama3:latest",
      messages: [{ role: "user", content: "Hello" }],
    });

    expect(response.provider).toBe("ollama");
    expect(response.model).toBe("llama3:latest");
    expect(response.tier).toBe(ModelTier.Haiku);
    expect(response.content).toBe("Hello! How can I help you?");
    expect(response.finishReason).toBe("stop");
    expect(response.usage).toEqual({ totalTokens: 42 });
  });

  test("chat response without eval_count omits usage", async () => {
    const noUsageResponse = { ...MOCK_CHAT_RESPONSE, eval_count: undefined };
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(noUsageResponse), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const response = await provider.chat({
      model: "llama3:latest",
      messages: [{ role: "user", content: "Hello" }],
    });

    expect(response.usage).toBeUndefined();
  });

  test("chat response with done=false has finishReason length", async () => {
    const partialResponse = { ...MOCK_CHAT_RESPONSE, done: false };
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(partialResponse), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const response = await provider.chat({
      model: "llama3:latest",
      messages: [{ role: "user", content: "Hello" }],
    });

    expect(response.finishReason).toBe("length");
  });

  test("chat with HTTP error throws", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response("Internal Server Error", { status: 500 })),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    await expect(
      provider.chat({
        model: "llama3:latest",
        messages: [{ role: "user", content: "Hello" }],
      }),
    ).rejects.toThrow("Ollama /api/chat returned 500");
  });
});

describe("OllamaProvider.listModels", () => {
  test("returns parsed model list", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(MOCK_MODELS_RESPONSE), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const models = await provider.listModels();

    expect(models).toHaveLength(2);
    expect(models[0].name).toBe("llama3:latest");
    expect(models[1].name).toBe("codellama:70b");
  });

  test("returns empty array when no models", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({}), { status: 200 })),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    const models = await provider.listModels();
    expect(models).toHaveLength(0);
  });
});

describe("OllamaProvider.inferTier", () => {
  test("small models map to Haiku", () => {
    expect(OllamaProvider.inferTier("llama3:latest")).toBe(ModelTier.Haiku);
    expect(OllamaProvider.inferTier("phi3:mini")).toBe(ModelTier.Haiku);
    expect(OllamaProvider.inferTier("gemma:7b")).toBe(ModelTier.Haiku);
  });

  test("large models map to Sonnet", () => {
    expect(OllamaProvider.inferTier("llama3:70b")).toBe(ModelTier.Sonnet);
    expect(OllamaProvider.inferTier("codellama:34b")).toBe(ModelTier.Sonnet);
    expect(OllamaProvider.inferTier("mixtral:latest")).toBe(ModelTier.Sonnet);
    expect(OllamaProvider.inferTier("codellama:latest")).toBe(ModelTier.Sonnet);
    expect(OllamaProvider.inferTier("llama2:65b")).toBe(ModelTier.Sonnet);
  });

  test("never maps to Opus", () => {
    const models = [
      "llama3:latest",
      "llama3:70b",
      "codellama:34b",
      "mixtral:latest",
      "phi3:mini",
      "gemma:7b",
      "codellama:latest",
      "qwen:110b",
    ];
    for (const model of models) {
      expect(OllamaProvider.inferTier(model)).not.toBe(ModelTier.Opus);
    }
  });
});

describe("OllamaProvider.isAvailable", () => {
  test("returns true when server responds 200", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify(MOCK_MODELS_RESPONSE), { status: 200 }),
      ),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    expect(await provider.isAvailable()).toBe(true);
  });

  test("returns false when server unreachable", async () => {
    globalThis.fetch = mock(() =>
      Promise.reject(new TypeError("fetch failed")),
    ) as unknown as typeof fetch;

    const provider = new OllamaProvider();
    expect(await provider.isAvailable()).toBe(false);
  });
});
