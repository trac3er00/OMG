import { afterAll, describe, it, expect } from "bun:test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();

describe("Host Parity: MCP Registration", () => {
  it("claude: .mcp.json exists with omg-control", () => {
    const config = JSON.parse(readFileSync(join(ROOT, ".mcp.json"), "utf8"));
    expect(config.mcpServers ?? config).toBeDefined();
    const content = JSON.stringify(config);
    expect(content).toContain("omg-control");
  });

  it("gemini: .gemini/settings.json exists with omg-control", () => {
    const configPath = join(ROOT, ".gemini", "settings.json");
    expect(existsSync(configPath)).toBe(true);
    const config = JSON.parse(readFileSync(configPath, "utf8"));
    expect(JSON.stringify(config)).toContain("omg-control");
  });

  it("kimi: .kimi/mcp.json exists with omg-control", () => {
    const configPath = join(ROOT, ".kimi", "mcp.json");
    expect(existsSync(configPath)).toBe(true);
    const config = JSON.parse(readFileSync(configPath, "utf8"));
    expect(JSON.stringify(config)).toContain("omg-control");
  });

  it("codex: .agents/skills/omg/ directory exists (codex uses skills not MCP config)", () => {
    expect(existsSync(join(ROOT, ".agents", "skills", "omg"))).toBe(true);
  });

  it("opencode: opencode.json or ~/.config/opencode/opencode.json documented in CLI-ADAPTER-MAP.md", () => {
    const adapterMap = readFileSync(join(ROOT, "CLI-ADAPTER-MAP.md"), "utf8");
    expect(adapterMap).toMatch(/opencode/i);
  });
});

describe("Host Parity: Skills Directories", () => {
  it("claude: skills/claude/ exists", () => {
    expect(existsSync(join(ROOT, "skills", "claude"))).toBe(true);
  });

  it("codex: skills/codex/ exists", () => {
    expect(existsSync(join(ROOT, "skills", "codex"))).toBe(true);
  });

  it("gemini: skills/gemini/ exists", () => {
    expect(existsSync(join(ROOT, "skills", "gemini"))).toBe(true);
  });

  it("kimi: skills/kimi/ exists (created in T9)", () => {
    expect(existsSync(join(ROOT, "skills", "kimi"))).toBe(true);
  });

  it("opencode: skills/opencode/ exists", () => {
    expect(existsSync(join(ROOT, "skills", "opencode"))).toBe(true);
  });
});

describe("Host Parity: Hook Emulation", () => {
  it("hook-emulation module exists for non-Claude hosts", () => {
    expect(existsSync(join(ROOT, "src", "compat", "hook-emulation.ts"))).toBe(
      true,
    );
  });

  it("support-matrix declares all 5 hosts", () => {
    const matrix = JSON.parse(
      readFileSync(join(ROOT, "support-matrix.json"), "utf8"),
    );
    const all = [
      ...(matrix.canonical_hosts ?? []),
      ...(matrix.compatibility_hosts ?? []),
    ];
    expect(all).toContain("claude");
    expect(all).toContain("codex");
    expect(all).toContain("gemini");
    expect(all).toContain("kimi");
    expect(all).toContain("opencode");
  });
});

afterAll(() => {
  const evidence = {
    timestamp: new Date().toISOString(),
    hosts: ["claude", "codex", "gemini", "kimi", "opencode"],
    mcpRegistration: {
      claude: existsSync(join(ROOT, ".mcp.json")),
      gemini: existsSync(join(ROOT, ".gemini", "settings.json")),
      kimi: existsSync(join(ROOT, ".kimi", "mcp.json")),
      codex: "skills-based",
      opencode: "documented",
    },
    skillsDirectories: {
      claude: existsSync(join(ROOT, "skills", "claude")),
      codex: existsSync(join(ROOT, "skills", "codex")),
      gemini: existsSync(join(ROOT, "skills", "gemini")),
      kimi: existsSync(join(ROOT, "skills", "kimi")),
      opencode: existsSync(join(ROOT, "skills", "opencode")),
    },
  };

  mkdirSync(join(ROOT, ".sisyphus", "evidence"), { recursive: true });
  writeFileSync(
    join(ROOT, ".sisyphus", "evidence", "task-11-host-parity.json"),
    JSON.stringify(evidence, null, 2),
  );
});
