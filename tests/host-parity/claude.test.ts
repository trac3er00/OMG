import { describe, test, expect } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();

describe("Claude host parity", () => {
  test("Claude install guide exists", () => {
    expect(existsSync(join(ROOT, "docs/install/claude-code.md"))).toBe(true);
  });

  test("Claude plugin config exists", () => {
    expect(existsSync(join(ROOT, ".claude-plugin"))).toBe(true);
  });

  test("Control plane MCP server exists", () => {
    expect(existsSync(join(ROOT, "src/mcp/server.ts"))).toBe(true);
  });

  test("OMG skills directory exists", () => {
    expect(existsSync(join(ROOT, ".agents/skills/omg"))).toBe(true);
  });
});
