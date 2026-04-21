/**
 * Ollama provider adapter.
 * Implements BaseCliProvider for the Ollama local model server.
 * Uses HTTP API at localhost:11434 instead of CLI auth.
 */

import type { HostSurface } from "../runtime/canonical-surface.js";
import { getHostSurface } from "../runtime/canonical-surface.js";
import type { CliHealthStatus } from "../runtime/cli-provider.js";
import { BaseCliProvider } from "../runtime/cli-provider.js";
import type { HostType } from "../types/config.js";
import { ModelTier } from "../orchestration/router.js";

const DEFAULT_BASE_URL = "http://localhost:11434";
const HEALTH_TIMEOUT_MS = 5_000;
const CHAT_TIMEOUT_MS = 30_000;

export interface OllamaProviderOptions {
  readonly healthTimeoutMs?: number;
  readonly chatTimeoutMs?: number;
}

export interface OllamaChatMessage {
  readonly role: "system" | "user" | "assistant";
  readonly content: string;
}

export interface OllamaChatRequest {
  readonly model: string;
  readonly messages: OllamaChatMessage[];
  readonly stream?: boolean;
}

export interface OllamaModelInfo {
  readonly name: string;
  readonly size: number;
  readonly digest: string;
  readonly modified_at: string;
}

export interface NormalizedChatResponse {
  readonly provider: "ollama";
  readonly model: string;
  readonly tier: ModelTier;
  readonly content: string;
  readonly finishReason: "stop" | "length" | "error";
  readonly usage?: { readonly totalTokens?: number };
}

export class OllamaChatTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Ollama chat request timed out after ${timeoutMs}ms`);
    this.name = "OllamaChatTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

export class OllamaProvider extends BaseCliProvider {
  readonly hostType: HostType = "ollama";
  readonly surface: HostSurface = getHostSurface("ollama");
  readonly baseUrl: string;
  private readonly healthTimeoutMs: number;
  private readonly chatTimeoutMs: number;

  constructor(
    baseUrl: string = DEFAULT_BASE_URL,
    options: OllamaProviderOptions = {},
  ) {
    super();
    this.baseUrl = baseUrl;
    this.healthTimeoutMs = normalizeTimeout(
      options.healthTimeoutMs,
      HEALTH_TIMEOUT_MS,
    );
    this.chatTimeoutMs = normalizeTimeout(
      options.chatTimeoutMs,
      CHAT_TIMEOUT_MS,
    );
  }

  async healthCheck(): Promise<CliHealthStatus> {
    try {
      const models = await this.listModels();
      return this.makeHealthStatus(
        true,
        true,
        true,
        `Ollama server running with ${models.length} model(s) available`,
      );
    } catch (err: unknown) {
      const isConnRefused =
        err instanceof TypeError ||
        (err instanceof Error &&
          (err.message.includes("ECONNREFUSED") ||
            err.message.includes("fetch failed")));
      if (isConnRefused) {
        return this.makeHealthStatus(
          false,
          false,
          false,
          `Ollama server not reachable at ${this.baseUrl}`,
          "Install: https://ollama.ai and run: ollama serve",
        );
      }
      return this.makeHealthStatus(
        false,
        false,
        false,
        `Ollama health check failed: ${err instanceof Error ? err.message : String(err)}`,
        "Install: https://ollama.ai and run: ollama serve",
      );
    }
  }

  async listModels(): Promise<OllamaModelInfo[]> {
    const response = await this.fetchWithTimeout(
      `${this.baseUrl}/api/tags`,
      undefined,
      this.healthTimeoutMs,
    );
    if (!response.ok) {
      throw new Error(`Ollama /api/tags returned ${response.status}`);
    }
    const data = (await response.json()) as { models?: OllamaModelInfo[] };
    return data.models ?? [];
  }

  async chat(request: OllamaChatRequest): Promise<NormalizedChatResponse> {
    let response: Response;
    try {
      response = await this.fetchWithTimeout(
        `${this.baseUrl}/api/chat`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...request, stream: false }),
        },
        this.chatTimeoutMs,
      );
    } catch (err: unknown) {
      if (isAbortError(err)) {
        throw new OllamaChatTimeoutError(this.chatTimeoutMs);
      }
      throw err;
    }
    if (!response.ok) {
      throw new Error(`Ollama /api/chat returned ${response.status}`);
    }
    const data = (await response.json()) as {
      model?: string;
      message?: { content?: string };
      done?: boolean;
      eval_count?: number;
    };
    const responseModel = resolveModelName(data.model, request.model);
    const base = {
      provider: "ollama" as const,
      model: responseModel,
      tier: OllamaProvider.inferTier(responseModel),
      content: data.message?.content ?? "",
      finishReason: (data.done ? "stop" : "length") as "stop" | "length",
    };
    if (data.eval_count != null) {
      return { ...base, usage: { totalTokens: data.eval_count } };
    }
    return base;
  }

  static inferTier(modelName: string): ModelTier {
    const lower = modelName.toLowerCase();
    const mixtureSizes = Array.from(
      lower.matchAll(/(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*b/g),
    ).map((match) => Number(match[1]) * Number(match[2]));
    const modelSizes = Array.from(lower.matchAll(/(\d+(?:\.\d+)?)\s*b\b/g)).map(
      (match) => Number(match[1]),
    );

    if (
      mixtureSizes.some((size) => Number.isFinite(size) && size >= 30) ||
      modelSizes.some((size) => Number.isFinite(size) && size >= 30)
    ) {
      return ModelTier.Sonnet;
    }

    const isSonnet = lower.includes("mixtral") || lower.includes("codellama");
    return isSonnet ? ModelTier.Sonnet : ModelTier.Haiku;
  }

  getMcpConfig(
    serverCommand: string,
    serverArgs: string[],
  ): Record<string, unknown> {
    return {
      mcpServers: {
        "omg-control": {
          command: serverCommand,
          args: serverArgs,
        },
      },
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      const response = await this.fetchWithTimeout(
        `${this.baseUrl}/api/tags`,
        undefined,
        this.healthTimeoutMs,
      );
      return response.ok;
    } catch {
      return false;
    }
  }

  private async fetchWithTimeout(
    url: string,
    init?: RequestInit,
    timeoutMs: number = this.healthTimeoutMs,
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
}

function normalizeTimeout(
  candidate: number | undefined,
  fallback: number,
): number {
  if (typeof candidate !== "number") {
    return fallback;
  }
  if (!Number.isFinite(candidate) || candidate <= 0) {
    return fallback;
  }
  return Math.floor(candidate);
}

function resolveModelName(
  responseModel: string | undefined,
  requestModel: string,
): string {
  const trimmed = responseModel?.trim();
  if (trimmed && trimmed.length > 0) {
    return trimmed;
  }
  return requestModel;
}

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException) {
    return err.name === "AbortError";
  }
  return err instanceof Error && err.name === "AbortError";
}
