import type { HostSurface } from "../runtime/canonical-surface.js";
import { getHostSurface } from "../runtime/canonical-surface.js";
import type { CliHealthStatus } from "../runtime/cli-provider.js";
import { BaseCliProvider } from "../runtime/cli-provider.js";
import type { HostType } from "../types/config.js";
import { ModelTier } from "../orchestration/router.js";

const DEFAULT_BASE_URL = "https://ollama.com/api";
const API_KEY_ENV = "OLLAMA_API_KEY";
const HEALTH_TIMEOUT_MS = 5_000;
const CHAT_TIMEOUT_MS = 30_000;

export interface OllamaCloudProviderOptions {
  readonly healthTimeoutMs?: number;
  readonly chatTimeoutMs?: number;
}

export interface OllamaCloudChatMessage {
  readonly role: "system" | "user" | "assistant";
  readonly content: string;
}

export interface OllamaCloudChatRequest {
  readonly model: string;
  readonly messages: OllamaCloudChatMessage[];
  readonly stream?: boolean;
}

export interface OllamaCloudModelInfo {
  readonly name: string;
  readonly size: number;
  readonly digest: string;
  readonly modified_at: string;
}

export interface OllamaCloudNormalizedChatResponse {
  readonly provider: "ollama-cloud";
  readonly model: string;
  readonly tier: ModelTier;
  readonly content: string;
  readonly finishReason: "stop" | "length" | "error";
  readonly usage?: { readonly totalTokens?: number };
}

export class OllamaCloudChatTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Ollama Cloud chat request timed out after ${timeoutMs}ms`);
    this.name = "OllamaCloudChatTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

export class OllamaCloudProvider extends BaseCliProvider {
  readonly hostType: HostType = "ollama-cloud";
  readonly surface: HostSurface = getHostSurface("ollama-cloud");
  readonly baseUrl: string;
  private readonly healthTimeoutMs: number;
  private readonly chatTimeoutMs: number;

  constructor(
    baseUrl: string = DEFAULT_BASE_URL,
    options: OllamaCloudProviderOptions = {},
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
    const apiKey = getApiKeyFromEnv();
    if (!apiKey) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        `${API_KEY_ENV} is not set`,
        `Set ${API_KEY_ENV} from https://ollama.com/settings/keys`,
      );
    }

    try {
      const models = await this.listModels();
      return this.makeHealthStatus(
        true,
        true,
        true,
        `Ollama Cloud reachable with ${models.length} model(s) available`,
      );
    } catch (err: unknown) {
      if (isUnauthorizedError(err)) {
        return this.makeHealthStatus(
          true,
          false,
          true,
          "Ollama Cloud reachable but API key is invalid or unauthorized",
          `Regenerate ${API_KEY_ENV} at https://ollama.com/settings/keys`,
        );
      }

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
          `Ollama Cloud not reachable at ${this.baseUrl}`,
          "Check network access to https://ollama.com/api",
        );
      }

      return this.makeHealthStatus(
        false,
        false,
        false,
        `Ollama Cloud health check failed: ${err instanceof Error ? err.message : String(err)}`,
        `Set ${API_KEY_ENV} from https://ollama.com/settings/keys`,
      );
    }
  }

  async listModels(): Promise<OllamaCloudModelInfo[]> {
    const apiKey = this.getRequiredApiKey();
    const response = await this.fetchWithTimeout(
      `${this.baseUrl}/tags`,
      {
        headers: this.makeAuthHeaders(apiKey),
      },
      this.healthTimeoutMs,
    );
    if (!response.ok) {
      throw new Error(`Ollama Cloud /api/tags returned ${response.status}`);
    }
    const data = (await response.json()) as { models?: OllamaCloudModelInfo[] };
    return data.models ?? [];
  }

  async chat(
    request: OllamaCloudChatRequest,
  ): Promise<OllamaCloudNormalizedChatResponse> {
    const apiKey = this.getRequiredApiKey();
    let response: Response;
    try {
      response = await this.fetchWithTimeout(
        `${this.baseUrl}/chat`,
        {
          method: "POST",
          headers: this.makeAuthHeaders(apiKey, {
            "Content-Type": "application/json",
          }),
          body: JSON.stringify({ ...request, stream: false }),
        },
        this.chatTimeoutMs,
      );
    } catch (err: unknown) {
      if (isAbortError(err)) {
        throw new OllamaCloudChatTimeoutError(this.chatTimeoutMs);
      }
      throw err;
    }
    if (!response.ok) {
      throw new Error(`Ollama Cloud /api/chat returned ${response.status}`);
    }
    const data = (await response.json()) as {
      model?: string;
      message?: { content?: string };
      done?: boolean;
      eval_count?: number;
    };

    const responseModel = resolveModelName(data.model, request.model);
    const base = {
      provider: "ollama-cloud" as const,
      model: responseModel,
      tier: OllamaCloudProvider.inferTier(responseModel),
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
      mixtureSizes.some((size) => Number.isFinite(size) && size >= 100) ||
      modelSizes.some((size) => Number.isFinite(size) && size >= 100)
    ) {
      return ModelTier.Opus;
    }

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
    const apiKey = getApiKeyFromEnv();
    if (!apiKey) {
      return false;
    }

    try {
      const response = await this.fetchWithTimeout(
        `${this.baseUrl}/tags`,
        {
          headers: this.makeAuthHeaders(apiKey),
        },
        this.healthTimeoutMs,
      );
      return response.ok;
    } catch {
      return false;
    }
  }

  private getRequiredApiKey(): string {
    const apiKey = getApiKeyFromEnv();
    if (!apiKey) {
      throw new Error(`${API_KEY_ENV} is not set`);
    }
    return apiKey;
  }

  private makeAuthHeaders(
    apiKey: string,
    extra: Record<string, string> = {},
  ): Record<string, string> {
    return {
      ...extra,
      Authorization: `Bearer ${apiKey}`,
    };
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

function getApiKeyFromEnv(): string | undefined {
  const raw = process.env[API_KEY_ENV];
  const trimmed = raw?.trim();
  if (trimmed && trimmed.length > 0) {
    return trimmed;
  }
  return undefined;
}

function isUnauthorizedError(err: unknown): boolean {
  if (!(err instanceof Error)) {
    return false;
  }
  return err.message.includes("401") || err.message.includes("403");
}

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException) {
    return err.name === "AbortError";
  }
  return err instanceof Error && err.name === "AbortError";
}
