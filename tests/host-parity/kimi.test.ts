import { describe, test, expect } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = "/home/claw/src/OMG";

describe("Kimi host parity", () => {
  test("Kimi install guide exists", () => {
    expect(existsSync(join(ROOT, "docs/install/kimi.md"))).toBe(true);
  });
});
