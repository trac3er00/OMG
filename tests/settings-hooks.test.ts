import { describe, expect, test } from "bun:test";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR, run, tempDir } from "./helpers.ts";

describe("hook registrations", () => {
  test("shipped settings do not register no-op hooks", () => {
    const settings = JSON.parse(readFileSync(join(ROOT_DIR, "settings.json"), "utf8"));
    const configured = JSON.stringify(settings.hooks);
    expect(configured).not.toContain("pre-tool-inject.ts");
    expect(configured).not.toContain("test-generator-hook.ts");
    expect(configured).not.toContain("post-write.ts");
  });

  test("settings merge prunes retired no-op hooks from existing Claude settings", () => {
    const dir = tempDir("omg-hooks-");
    const targetPath = join(dir, "settings.json");
    writeFileSync(
      targetPath,
      JSON.stringify(
        {
          hooks: {
            PreToolUse: [
              {
                hooks: [{ type: "command", command: "\"$HOME/.claude/hooks/pre-tool-inject.ts\"" }]
              }
            ],
            PostToolUse: [
              {
                matcher: "Write|Edit|MultiEdit",
                hooks: [
                  { type: "command", command: "\"$HOME/.claude/hooks/tool-ledger.ts\"", timeout: 10 },
                  { type: "command", command: "\"$HOME/.claude/hooks/test-generator-hook.ts\"", timeout: 10 },
                  { type: "command", command: "\"$HOME/.claude/hooks/post-write.ts\"", timeout: 15 }
                ]
              }
            ]
          }
        },
        null,
        2
      )
    );

    const merge = run(["bun", "scripts/settings-merge.ts", targetPath, join(ROOT_DIR, "settings.json")], { cwd: ROOT_DIR });
    expect(merge.exitCode).toBe(0);

    const merged = JSON.parse(readFileSync(targetPath, "utf8"));
    const configured = JSON.stringify(merged.hooks);
    expect(configured).not.toContain("pre-tool-inject.ts");
    expect(configured).not.toContain("test-generator-hook.ts");
    expect(configured).not.toContain("post-write.ts");
    expect(configured).toContain("tool-ledger.ts");
  });
});
