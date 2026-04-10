import type { ICliProvider } from "../runtime/cli-provider.js";
import type { HostType } from "../types/config.js";
import { ClaudeProvider } from "./claude.js";
import { CodexProvider } from "./codex.js";
import { GeminiProvider } from "./gemini.js";
import { KimiProvider } from "./kimi.js";
import { OllamaProvider } from "./ollama.js";
import { OpenCodeProvider } from "./opencode.js";

const PROVIDER_MAP: ReadonlyMap<HostType, () => ICliProvider> = new Map([
  ["claude", () => new ClaudeProvider()],
  ["codex", () => new CodexProvider()],
  ["gemini", () => new GeminiProvider()],
  ["kimi", () => new KimiProvider()],
  ["ollama", () => new OllamaProvider()],
  ["opencode", () => new OpenCodeProvider()],
]);

export class ProviderRegistry {
  private readonly instances = new Map<HostType, ICliProvider>();

  getProvider(name: HostType): ICliProvider {
    const cached = this.instances.get(name);
    if (cached) return cached;

    const factory = PROVIDER_MAP.get(name);
    if (!factory) {
      throw new Error(`Unknown provider: ${name}`);
    }

    const instance = factory();
    this.instances.set(name, instance);
    return instance;
  }

  listProviders(): HostType[] {
    return [...PROVIDER_MAP.keys()];
  }
}

export { ClaudeProvider } from "./claude.js";
export { CodexProvider } from "./codex.js";
export { GeminiProvider } from "./gemini.js";
export { KimiProvider } from "./kimi.js";
export { OllamaProvider } from "./ollama.js";
export { OpenCodeProvider } from "./opencode.js";
