import { describe, test, expect } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = "/home/claw/src/OMG";

describe("OpenCode host parity", () => {
  test("OpenCode install guide exists", () => {
    expect(existsSync(join(ROOT, "docs/install/opencode.md"))).toBe(true);
  });

  test("OMG control plane server exists", () => {
    expect(existsSync(join(ROOT, "src/mcp/server.ts"))).toBe(true);
  });
});
