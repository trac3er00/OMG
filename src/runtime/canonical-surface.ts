/**
 * Canonical host/CLI surface definitions.
 * Maps between host types and their configuration formats.
 * Mirrors runtime/canonical_surface.py.
 */

import { execFile } from "node:child_process";
import type { HostType } from "../types/config.js";

export interface HostSurface {
  readonly hostType: HostType;
  readonly cliCommand: string;
  readonly configFormat:
    | "mcp-json"
    | "config-toml"
    | "settings-json"
    | "kimi-json";
  readonly configPath: string;
  readonly supportsHooks: boolean;
  readonly supportsPresets: boolean;
  readonly transportType: "stdio" | "http-sse";
  readonly description: string;
}

export const HOST_SURFACES: Record<HostType, HostSurface> = {
  claude: {
    hostType: "claude",
    cliCommand: "claude",
    configFormat: "mcp-json",
    configPath: ".mcp.json",
    supportsHooks: true,
    supportsPresets: true,
    transportType: "stdio",
    description: "Claude Code (Anthropic)",
  },
  codex: {
    hostType: "codex",
    cliCommand: "codex",
    configFormat: "config-toml",
    configPath: "config.toml",
    supportsHooks: true,
    supportsPresets: true,
    transportType: "stdio",
    description: "Codex CLI (OpenAI)",
  },
  gemini: {
    hostType: "gemini",
    cliCommand: "gemini",
    configFormat: "settings-json",
    configPath: ".gemini/settings.json",
    supportsHooks: true,
    supportsPresets: true,
    transportType: "stdio",
    description: "Gemini CLI (Google)",
  },
  kimi: {
    hostType: "kimi",
    cliCommand: "kimi",
    configFormat: "kimi-json",
    configPath: ".kimi/mcp.json",
    supportsHooks: true,
    supportsPresets: true,
    transportType: "stdio",
    description: "Kimi CLI (Moonshot AI)",
  },
  ollama: {
    hostType: "ollama",
    cliCommand: "ollama",
    configFormat: "mcp-json",
    configPath: ".mcp.json",
    supportsHooks: false,
    supportsPresets: false,
    transportType: "http-sse",
    description: "Ollama (local model server)",
  },
  "ollama-cloud": {
    hostType: "ollama-cloud",
    cliCommand: "ollama",
    configFormat: "mcp-json",
    configPath: "~/.ollama-cloud/mcp.json",
    supportsHooks: false,
    supportsPresets: false,
    transportType: "http-sse",
    description: "Ollama Cloud (hosted model server)",
  },
  opencode: {
    hostType: "opencode",
    cliCommand: "opencode",
    configFormat: "mcp-json",
    configPath: ".mcp.json",
    supportsHooks: false,
    supportsPresets: false,
    transportType: "stdio",
    description: "OpenCode (compatibility mode)",
  },
};

export const CANONICAL_HOSTS: HostType[] = [
  "claude",
  "codex",
  "gemini",
  "kimi",
  "ollama",
  "ollama-cloud",
  "opencode",
];
export const FULLY_SUPPORTED_HOSTS: HostType[] = [
  "claude",
  "codex",
  "gemini",
  "kimi",
];
export const COMPAT_HOSTS: HostType[] = ["opencode"];
export const LOCAL_HOSTS: HostType[] = ["ollama"];

export function getHostSurface(hostType: HostType): HostSurface {
  const surface = HOST_SURFACES[hostType];
  if (!surface) {
    throw new Error(`Unknown host type: ${hostType}`);
  }
  return surface;
}

async function probeCommandOnPath(command: string): Promise<boolean> {
  try {
    await new Promise<void>((resolve, reject) => {
      execFile("which", [command], (error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
    return true;
  } catch {
    return false;
  }
}

export async function isHostInstalled(
  hostType: HostType,
  probe: (command: string) => Promise<boolean> = probeCommandOnPath,
): Promise<boolean> {
  return probe(getHostSurface(hostType).cliCommand).catch(() => false);
}

export async function detectInstalledHosts(
  probe: (command: string) => Promise<boolean> = probeCommandOnPath,
): Promise<HostType[]> {
  const checks = await Promise.all(
    CANONICAL_HOSTS.map(async (host) => ({
      host,
      installed: await isHostInstalled(host, probe),
    })),
  );

  return checks.filter((check) => check.installed).map((check) => check.host);
}
