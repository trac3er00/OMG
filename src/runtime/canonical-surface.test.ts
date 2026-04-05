import { describe, expect, test } from "bun:test";
import { CANONICAL_HOSTS, COMPAT_HOSTS, FULLY_SUPPORTED_HOSTS, HOST_SURFACES, detectInstalledHosts, getHostSurface, isHostInstalled } from "./canonical-surface.js";
import { getTierCapabilities } from "./canonical-taxonomy.js";
import { needsUpgrade, selectDefaultPreset } from "./adoption.js";

describe("Host surfaces", () => {
  test("all canonical hosts are defined", () => {
    for (const host of CANONICAL_HOSTS) {
      expect(HOST_SURFACES[host]).toBeDefined();
    }
    expect(COMPAT_HOSTS).toEqual(["opencode"]);
  });

  test("Claude Code is recognized", () => {
    const surface = getHostSurface("claude");
    expect(surface.hostType).toBe("claude");
    expect(surface.configFormat).toBe("mcp-json");
    expect(surface.supportsHooks).toBe(true);
  });

  test("Codex is recognized", () => {
    const surface = getHostSurface("codex");
    expect(surface.hostType).toBe("codex");
    expect(surface.configFormat).toBe("config-toml");
  });

  test("Gemini CLI is recognized", () => {
    const surface = getHostSurface("gemini");
    expect(surface.hostType).toBe("gemini");
    expect(surface.configFormat).toBe("settings-json");
  });

  test("Kimi CLI is recognized", () => {
    const surface = getHostSurface("kimi");
    expect(surface.hostType).toBe("kimi");
    expect(surface.configFormat).toBe("kimi-json");
  });

  test("OpenCode is recognized", () => {
    const surface = getHostSurface("opencode");
    expect(surface.hostType).toBe("opencode");
    expect(surface.supportsHooks).toBe(false);
    expect(surface.supportsPresets).toBe(false);
  });

  test("fully supported hosts have hooks support", () => {
    for (const host of FULLY_SUPPORTED_HOSTS) {
      expect(HOST_SURFACES[host]?.supportsHooks).toBe(true);
    }
  });
});

describe("Host detection", () => {
  const installed = new Set(["claude", "codex", "gemini", "kimi", "opencode"]);

  const probe = async (command: string): Promise<boolean> => installed.has(command);

  test("isHostInstalled uses the CLI command", async () => {
    expect(await isHostInstalled("claude", probe)).toBe(true);
    expect(await isHostInstalled("codex", probe)).toBe(true);
    expect(await isHostInstalled("opencode", async () => false)).toBe(false);
  });

  test("detectInstalledHosts returns all installed canonical hosts", async () => {
    const detected = await detectInstalledHosts(probe);
    expect(detected).toEqual(CANONICAL_HOSTS);
  });
});

describe("Adoption", () => {
  test("coexist mode selects interop preset", () => {
    expect(selectDefaultPreset("coexist", 2)).toBe("interop");
  });

  test("no hosts selects safe preset", () => {
    expect(selectDefaultPreset("omg-only", 0)).toBe("safe");
  });

  test("one host selects balanced preset", () => {
    expect(selectDefaultPreset("omg-only", 1)).toBe("balanced");
  });

  test("upgrade detection compares canonical version", () => {
    expect(needsUpgrade("2.3.0")).toBe(false);
    expect(needsUpgrade("2.9.9")).toBe(true);
  });
});

describe("Taxonomy", () => {
  test("enterprise tier has max capabilities", () => {
    const caps = getTierCapabilities("enterprise");
    expect(caps.maxAgents).toBe(999);
    expect(caps.hasForge).toBe(true);
  });

  test("community tier has no forge", () => {
    const caps = getTierCapabilities("community");
    expect(caps.hasForge).toBe(false);
  });
});
