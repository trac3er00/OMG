import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR } from "./helpers.ts";

const VERSIONED_FILES = [
  "package.json",
  "README.md",
  "settings.json",
  ".claude-plugin/plugin.json",
  ".claude-plugin/marketplace.json",
  "plugins/core/plugin.json",
  "plugins/advanced/plugin.json",
  "runtime/compat.ts"
];

describe("stable metadata", () => {
  test("all shipped release surfaces report v2.0.0 and no beta markers", () => {
    for (const file of VERSIONED_FILES) {
      const content = readFileSync(join(ROOT_DIR, file), "utf8");
      expect(content).not.toContain("2.0.0-beta.6");
      expect(content).not.toContain("v2.0.0-beta.6");
    }

    const pkg = JSON.parse(readFileSync(join(ROOT_DIR, "package.json"), "utf8"));
    expect(pkg.version).toBe("2.0.0");
  });
});
