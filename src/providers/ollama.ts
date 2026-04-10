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

export class OllamaProvider extends BaseCliProvider {
  readonly hostType: HostType = "ollama";
  readonly surface: HostSurface = getHostSurface("ollama");
  readonly baseUrl: string;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    super();
    this.baseUrl = baseUrl;
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
    const response = await this.fetchWithTimeout(`${this.baseUrl}/api/tags`);
    if (!response.ok) {
      throw new Error(`Ollama /api/tags returned ${response.status}`);
    }
    const data = (await response.json()) as { models?: OllamaModelInfo[] };
    return data.models ?? [];
  }

  async chat(request: OllamaChatRequest): Promise<NormalizedChatResponse> {
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, stream: false }),
    });
    if (!response.ok) {
      throw new Error(`Ollama /api/chat returned ${response.status}`);
    }
    const data = (await response.json()) as {
      model: string;
      message?: { content?: string };
      done?: boolean;
      eval_count?: number;
    };
    const base = {
      provider: "ollama" as const,
      model: data.model,
      tier: OllamaProvider.inferTier(data.model),
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
    const isSonnet =
      lower.includes("70b") ||
      lower.includes("34b") ||
      lower.includes("65b") ||
      lower.includes("mixtral") ||
      lower.includes("codellama");
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
      const response = await this.fetchWithTimeout(`${this.baseUrl}/api/tags`);
      return response.ok;
    } catch {
      return false;
    }
  }

  private async fetchWithTimeout(
    url: string,
    init?: RequestInit,
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
}
