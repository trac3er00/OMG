import { describe, test, expect } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = "/home/claw/src/OMG";

describe("Gemini host parity", () => {
  test("Gemini install guide exists", () => {
    expect(existsSync(join(ROOT, "docs/install/gemini.md"))).toBe(true);
  });

  test("Gemini settings exists", () => {
    expect(existsSync(join(ROOT, ".gemini"))).toBe(true);
  });
});
