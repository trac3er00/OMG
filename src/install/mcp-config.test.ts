import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";
import {
  generateMcpConfig,
  writeMcpConfig,
  resolveConfigPath,
  serializeConfig,
  type ClaudeConfig,
  type CodexConfig,
  type GeminiConfig,
  type KimiConfig,
  create,
} from "./mcp-config.js";

function makeTmpDir(): string {
  const dir = join(tmpdir(), `omg-test-${randomBytes(6).toString("hex")}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

describe("generateMcpConfig", () => {
  test("claude config has omg-control with bunx", () => {
    const config = generateMcpConfig("claude") as ClaudeConfig;
    expect(config.mcpServers["omg-control"]).toBeDefined();
    expect(config.mcpServers["omg-control"].command).toBe("bunx");
    expect(config.mcpServers["omg-control"].args).toEqual(["@trac3r/oh-my-god"]);
  });

  test("codex config uses mcp_servers key", () => {
    const config = generateMcpConfig("codex") as CodexConfig;
    expect(config.mcp_servers["omg-control"]).toBeDefined();
    expect(config.mcp_servers["omg-control"].command).toBe("bunx");
  });

  test("gemini config has omg-control", () => {
    const config = generateMcpConfig("gemini") as GeminiConfig;
    expect(config.mcpServers["omg-control"]).toBeDefined();
    expect(config.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("kimi config has omg-control", () => {
    const config = generateMcpConfig("kimi") as KimiConfig;
    expect(config.mcpServers["omg-control"]).toBeDefined();
    expect(config.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("custom server path is used", () => {
    const config = generateMcpConfig("claude", "./my-server") as ClaudeConfig;
    expect(config.mcpServers["omg-control"].args).toEqual(["./my-server"]);
  });
});

describe("serializeConfig", () => {
  test("claude serializes to JSON", () => {
    const config = generateMcpConfig("claude");
    const serialized = serializeConfig("claude", config);
    const parsed = JSON.parse(serialized);
    expect(parsed.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("codex serializes to TOML", () => {
    const config = generateMcpConfig("codex");
    const serialized = serializeConfig("codex", config);
    expect(serialized).toContain("[mcp_servers.omg-control]");
    expect(serialized).toContain('command = "bunx"');
    expect(serialized).toContain('"@trac3r/oh-my-god"');
  });
});

describe("resolveConfigPath", () => {
  test("claude resolves to .mcp.json in project dir", () => {
    const path = resolveConfigPath("claude", "/tmp/myproject");
    expect(path).toBe("/tmp/myproject/.mcp.json");
  });

  test("codex resolves to ~/.codex/config.toml", () => {
    const path = resolveConfigPath("codex");
    expect(path).toContain(".codex/config.toml");
  });

  test("gemini resolves to ~/.gemini/settings.json", () => {
    const path = resolveConfigPath("gemini");
    expect(path).toContain(".gemini/settings.json");
  });

  test("kimi resolves to ~/.kimi/mcp.json", () => {
    const path = resolveConfigPath("kimi");
    expect(path).toContain(".kimi/mcp.json");
  });
});

describe("writeMcpConfig", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = makeTmpDir();
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  test("writes claude .mcp.json", () => {
    const configPath = join(tmpDir, ".mcp.json");
    writeMcpConfig("claude", "@trac3r/oh-my-god", { configPath });
    expect(existsSync(configPath)).toBe(true);
    const content = JSON.parse(readFileSync(configPath, "utf8"));
    expect(content.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("writes codex config.toml", () => {
    const configPath = join(tmpDir, "config.toml");
    writeMcpConfig("codex", "@trac3r/oh-my-god", { configPath });
    expect(existsSync(configPath)).toBe(true);
    const content = readFileSync(configPath, "utf8");
    expect(content).toContain("[mcp_servers.omg-control]");
  });

  test("writes gemini settings.json", () => {
    const configPath = join(tmpDir, "settings.json");
    writeMcpConfig("gemini", "@trac3r/oh-my-god", { configPath });
    const content = JSON.parse(readFileSync(configPath, "utf8"));
    expect(content.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("writes kimi mcp.json", () => {
    const configPath = join(tmpDir, "mcp.json");
    writeMcpConfig("kimi", "@trac3r/oh-my-god", { configPath });
    const content = JSON.parse(readFileSync(configPath, "utf8"));
    expect(content.mcpServers["omg-control"].command).toBe("bunx");
  });

  test("merges into existing claude config", () => {
    const configPath = join(tmpDir, ".mcp.json");
    writeFileSync(configPath, JSON.stringify({
      mcpServers: { "other-server": { command: "node", args: ["other.js"] } },
    }, null, 2));
    writeMcpConfig("claude", "@trac3r/oh-my-god", { configPath });
    const content = JSON.parse(readFileSync(configPath, "utf8"));
    expect(content.mcpServers["omg-control"]).toBeDefined();
    expect(content.mcpServers["other-server"]).toBeDefined();
  });
});

describe("create factory", () => {
  test("returns writer with all methods", () => {
    const writer = create();
    expect(typeof writer.generateMcpConfig).toBe("function");
    expect(typeof writer.writeMcpConfig).toBe("function");
    expect(typeof writer.resolveConfigPath).toBe("function");
    expect(typeof writer.serializeConfig).toBe("function");
  });
});
