import { describe, expect, test } from "bun:test";
import { ClaudeProvider } from "./claude.js";
import { CodexProvider } from "./codex.js";
import { GeminiProvider } from "./gemini.js";
import { KimiProvider } from "./kimi.js";
import { OpenCodeProvider } from "./opencode.js";
import { ProviderRegistry } from "./index.js";

describe("ClaudeProvider", () => {
  const provider = new ClaudeProvider();

  test("hostType is claude", () => {
    expect(provider.hostType).toBe("claude");
  });

  test("surface matches claude host", () => {
    expect(provider.surface.hostType).toBe("claude");
    expect(provider.surface.cliCommand).toBe("claude");
    expect(provider.surface.configFormat).toBe("mcp-json");
  });

  test("healthCheck returns CliHealthStatus shape", async () => {
    const status = await provider.healthCheck();
    expect(typeof status.available).toBe("boolean");
    expect(typeof status.authOk).toBe("boolean");
    expect(typeof status.liveConnection).toBe("boolean");
    expect(typeof status.statusMessage).toBe("string");
    expect(status.statusMessage.length).toBeGreaterThan(0);
  });

  test("getMcpConfig returns mcpServers format", () => {
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

  test("getConfigPath includes surface configPath", () => {
    const path = provider.getConfigPath("/home/user/project");
    expect(path).toBe("/home/user/project/.mcp.json");
  });
});

describe("CodexProvider", () => {
  const provider = new CodexProvider();

  test("hostType is codex", () => {
    expect(provider.hostType).toBe("codex");
  });

  test("surface matches codex host", () => {
    expect(provider.surface.hostType).toBe("codex");
    expect(provider.surface.cliCommand).toBe("codex");
    expect(provider.surface.configFormat).toBe("config-toml");
  });

  test("healthCheck returns CliHealthStatus shape", async () => {
    const status = await provider.healthCheck();
    expect(typeof status.available).toBe("boolean");
    expect(typeof status.authOk).toBe("boolean");
    expect(typeof status.liveConnection).toBe("boolean");
    expect(typeof status.statusMessage).toBe("string");
  });

  test("getMcpConfig returns mcp_servers format for TOML", () => {
    const config = provider.getMcpConfig("npx", ["@trac3r/oh-my-god"]);
    expect(config).toEqual({
      mcp_servers: {
        "omg-control": {
          command: "npx",
          args: ["@trac3r/oh-my-god"],
        },
      },
    });
  });
});

describe("GeminiProvider", () => {
  const provider = new GeminiProvider();

  test("hostType is gemini", () => {
    expect(provider.hostType).toBe("gemini");
  });

  test("surface matches gemini host", () => {
    expect(provider.surface.hostType).toBe("gemini");
    expect(provider.surface.cliCommand).toBe("gemini");
    expect(provider.surface.configFormat).toBe("settings-json");
  });

  test("healthCheck returns CliHealthStatus shape", async () => {
    const status = await provider.healthCheck();
    expect(typeof status.available).toBe("boolean");
    expect(typeof status.authOk).toBe("boolean");
    expect(typeof status.liveConnection).toBe("boolean");
    expect(typeof status.statusMessage).toBe("string");
  });

  test("getMcpConfig returns mcpServers format", () => {
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

describe("KimiProvider", () => {
  const provider = new KimiProvider();

  test("hostType is kimi", () => {
    expect(provider.hostType).toBe("kimi");
  });

  test("surface matches kimi host", () => {
    expect(provider.surface.hostType).toBe("kimi");
    expect(provider.surface.cliCommand).toBe("kimi");
    expect(provider.surface.configFormat).toBe("kimi-json");
  });

  test("healthCheck returns CliHealthStatus shape", async () => {
    const status = await provider.healthCheck();
    expect(typeof status.available).toBe("boolean");
    expect(typeof status.authOk).toBe("boolean");
    expect(typeof status.liveConnection).toBe("boolean");
    expect(typeof status.statusMessage).toBe("string");
  });

  test("getMcpConfig returns mcpServers format", () => {
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

describe("OpenCodeProvider", () => {
  const provider = new OpenCodeProvider();

  test("hostType is opencode", () => {
    expect(provider.hostType).toBe("opencode");
  });

  test("surface matches opencode host", () => {
    expect(provider.surface.hostType).toBe("opencode");
    expect(provider.surface.cliCommand).toBe("opencode");
    expect(provider.surface.configFormat).toBe("mcp-json");
    expect(provider.surface.supportsHooks).toBe(false);
  });

  test("healthCheck returns CliHealthStatus shape", async () => {
    const status = await provider.healthCheck();
    expect(typeof status.available).toBe("boolean");
    expect(typeof status.authOk).toBe("boolean");
    expect(typeof status.liveConnection).toBe("boolean");
    expect(typeof status.statusMessage).toBe("string");
  });

  test("getMcpConfig returns opencode mcp format with stdio type", () => {
    const config = provider.getMcpConfig("npx", ["@trac3r/oh-my-god"]);
    expect(config).toEqual({
      mcp: {
        "omg-control": {
          type: "stdio",
          command: "npx",
          args: ["@trac3r/oh-my-god"],
        },
      },
    });
  });
});

describe("ProviderRegistry", () => {
  const registry = new ProviderRegistry();

  test("listProviders returns all 5 canonical hosts", () => {
    const providers = registry.listProviders();
    expect(providers).toContain("claude");
    expect(providers).toContain("codex");
    expect(providers).toContain("gemini");
    expect(providers).toContain("kimi");
    expect(providers).toContain("opencode");
    expect(providers).toHaveLength(5);
  });

  test("getProvider returns correct provider by name", () => {
    const claude = registry.getProvider("claude");
    expect(claude.hostType).toBe("claude");

    const codex = registry.getProvider("codex");
    expect(codex.hostType).toBe("codex");
  });

  test("getProvider caches instances", () => {
    const first = registry.getProvider("gemini");
    const second = registry.getProvider("gemini");
    expect(first).toBe(second);
  });

  test("getProvider throws for unknown provider", () => {
    expect(() => registry.getProvider("unknown" as "claude")).toThrow("Unknown provider: unknown");
  });

  test("all providers health-check without throwing", async () => {
    const providers = registry.listProviders();
    for (const name of providers) {
      const provider = registry.getProvider(name);
      const status = await provider.healthCheck();
      expect(typeof status.available).toBe("boolean");
      expect(typeof status.authOk).toBe("boolean");
      expect(typeof status.statusMessage).toBe("string");
    }
  });
});
