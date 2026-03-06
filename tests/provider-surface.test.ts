import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR, run, stdoutJson } from "./helpers.ts";

describe("provider surface", () => {
  test("stable release exposes only codex, gemini, and kimi", () => {
    const status = stdoutJson(run(["bun", "scripts/omg.ts", "providers", "status", "--smoke"]));
    const providers = status.providers.map((entry: any) => entry.provider);
    expect(providers).toEqual(["codex", "gemini", "kimi"]);

    const content =
      readFileSync(join(ROOT_DIR, "README.md"), "utf8") +
      readFileSync(join(ROOT_DIR, "plugins/README.md"), "utf8") +
      readFileSync(join(ROOT_DIR, "hud/omg-hud.mjs"), "utf8");
    expect(content.toLowerCase()).not.toContain("opencode");
  });
});
