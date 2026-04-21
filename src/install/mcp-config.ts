import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export const McpHostSchema = z.enum([
  "claude",
  "codex",
  "gemini",
  "kimi",
  "ollama-cloud",
]);
export type McpHost = z.infer<typeof McpHostSchema>;

export interface McpStdioEntry {
  readonly command: string;
  readonly args: readonly string[];
}

export interface ClaudeConfig {
  readonly mcpServers: {
    readonly [name: string]: McpStdioEntry;
  };
}

export interface CodexConfig {
  readonly mcp_servers: {
    readonly [name: string]: {
      readonly command: string;
      readonly args: readonly string[];
    };
  };
}

export interface GeminiConfig {
  readonly mcpServers: {
    readonly [name: string]: McpStdioEntry;
  };
}

export interface KimiConfig {
  readonly mcpServers: {
    readonly [name: string]: McpStdioEntry;
  };
}

export interface OllamaCloudConfig {
  readonly mcpServers: {
    readonly [name: string]: McpStdioEntry;
  };
}

export type McpConfigResult =
  | ClaudeConfig
  | CodexConfig
  | GeminiConfig
  | KimiConfig
  | OllamaCloudConfig;

// ---------------------------------------------------------------------------
// Config generators (pure — no file I/O)
// ---------------------------------------------------------------------------

function generateClaudeConfig(serverPath: string): ClaudeConfig {
  return {
    mcpServers: {
      "omg-control": {
        command: "bunx",
        args: [serverPath],
      },
    },
  };
}

function generateCodexConfig(serverPath: string): CodexConfig {
  return {
    mcp_servers: {
      "omg-control": {
        command: "bunx",
        args: [serverPath],
      },
    },
  };
}

function generateGeminiConfig(serverPath: string): GeminiConfig {
  return {
    mcpServers: {
      "omg-control": {
        command: "bunx",
        args: [serverPath],
      },
    },
  };
}

function generateKimiConfig(serverPath: string): KimiConfig {
  return {
    mcpServers: {
      "omg-control": {
        command: "bunx",
        args: [serverPath],
      },
    },
  };
}

function generateOllamaCloudConfig(serverPath: string): OllamaCloudConfig {
  return {
    mcpServers: {
      "omg-control": {
        command: "bunx",
        args: [serverPath],
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

const DEFAULT_SERVER_PATH = "@trac3r/oh-my-god";

/**
 * Generate a host-specific MCP config object without writing to disk.
 */
export function generateMcpConfig(
  host: McpHost,
  serverPath: string = DEFAULT_SERVER_PATH,
): McpConfigResult {
  switch (host) {
    case "claude":
      return generateClaudeConfig(serverPath);
    case "codex":
      return generateCodexConfig(serverPath);
    case "gemini":
      return generateGeminiConfig(serverPath);
    case "kimi":
      return generateKimiConfig(serverPath);
    case "ollama-cloud":
      return generateOllamaCloudConfig(serverPath);
  }
}

/**
 * Resolve the default config file path for a given host.
 */
export function resolveConfigPath(host: McpHost, projectDir?: string): string {
  switch (host) {
    case "claude":
      return join(projectDir ?? process.cwd(), ".mcp.json");
    case "codex":
      return join(homedir(), ".codex", "config.toml");
    case "gemini":
      return join(homedir(), ".gemini", "settings.json");
    case "kimi":
      return join(homedir(), ".kimi", "mcp.json");
    case "ollama-cloud":
      return join(homedir(), ".ollama-cloud", "mcp.json");
  }
}

/**
 * Serialize the config object to the format expected by the host.
 */
export function serializeConfig(
  host: McpHost,
  config: McpConfigResult,
): string {
  if (host === "codex") {
    return serializeToToml(config as CodexConfig);
  }
  return JSON.stringify(config, null, 2) + "\n";
}

/**
 * Minimal TOML serializer for Codex config (no external dependency).
 * Produces the `[mcp_servers.<name>]` table format Codex expects.
 */
function serializeToToml(config: CodexConfig): string {
  const lines: string[] = [];
  for (const [name, entry] of Object.entries(config.mcp_servers)) {
    lines.push(`[mcp_servers.${name}]`);
    lines.push(`command = "${escapeTomlString(entry.command)}"`);
    const argsStr = entry.args
      .map((a) => `"${escapeTomlString(a as string)}"`)
      .join(", ");
    lines.push(`args = [${argsStr}]`);
    lines.push("");
  }
  return lines.join("\n");
}

function escapeTomlString(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

// ---------------------------------------------------------------------------
// File-system helpers
// ---------------------------------------------------------------------------

function loadJsonConfig(filePath: string): Record<string, unknown> {
  if (!existsSync(filePath)) {
    return {};
  }
  try {
    const raw = readFileSync(filePath, "utf8").trim();
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      !Array.isArray(parsed)
    ) {
      return parsed as Record<string, unknown>;
    }
    return {};
  } catch {
    return {};
  }
}

function ensureDir(filePath: string): void {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

function mergeJsonMcpServer(
  filePath: string,
  serverName: string,
  payload: McpStdioEntry,
): void {
  const existing = loadJsonConfig(filePath);
  const servers =
    typeof existing["mcpServers"] === "object" &&
    existing["mcpServers"] !== null
      ? { ...(existing["mcpServers"] as Record<string, unknown>) }
      : {};
  servers[serverName] = payload;
  const merged = { ...existing, mcpServers: servers };
  ensureDir(filePath);
  writeFileSync(filePath, JSON.stringify(merged, null, 2) + "\n", "utf8");
}

/**
 * Write MCP config for the specified host.
 *
 * - Claude: merges into `<projectDir>/.mcp.json`
 * - Codex: writes `~/.codex/config.toml` (TOML, full replace of mcp_servers section)
 * - Gemini: merges into `~/.gemini/settings.json`
 * - Kimi: merges into `~/.kimi/mcp.json`
 */
export function writeMcpConfig(
  host: McpHost,
  serverPath: string = DEFAULT_SERVER_PATH,
  options?: { readonly projectDir?: string; readonly configPath?: string },
): string {
  const config = generateMcpConfig(host, serverPath);
  const targetPath =
    options?.configPath ?? resolveConfigPath(host, options?.projectDir);
  const entry: McpStdioEntry = { command: "bunx", args: [serverPath] };

  switch (host) {
    case "claude":
      mergeJsonMcpServer(targetPath, "omg-control", entry);
      break;

    case "codex": {
      ensureDir(targetPath);
      writeFileSync(targetPath, serializeConfig("codex", config), "utf8");
      break;
    }

    case "gemini":
      mergeJsonMcpServer(targetPath, "omg-control", entry);
      break;

    case "kimi":
      mergeJsonMcpServer(targetPath, "omg-control", entry);
      break;

    case "ollama-cloud":
      mergeJsonMcpServer(targetPath, "omg-control", entry);
      break;
  }

  return targetPath;
}

// ---------------------------------------------------------------------------
// Factory (DI-friendly)
// ---------------------------------------------------------------------------

export interface McpConfigWriter {
  generateMcpConfig: typeof generateMcpConfig;
  writeMcpConfig: typeof writeMcpConfig;
  resolveConfigPath: typeof resolveConfigPath;
  serializeConfig: typeof serializeConfig;
}

export function create(): McpConfigWriter {
  return {
    generateMcpConfig,
    writeMcpConfig,
    resolveConfigPath,
    serializeConfig,
  };
}
