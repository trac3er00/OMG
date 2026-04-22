import { describe, test, expect } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();

describe("Codex host parity", () => {
  test("Codex install guide exists", () => {
    expect(existsSync(join(ROOT, "docs/install/codex.md"))).toBe(true);
  });

  test("Codex rules skill exists", () => {
    expect(existsSync(join(ROOT, ".agents/skills/omg/codex-rules.md"))).toBe(
      true,
    );
  });

  test("Codex MCP config template exists", () => {
    expect(existsSync(join(ROOT, ".agents/skills/omg/codex-mcp.toml"))).toBe(
      true,
    );
  });
});
