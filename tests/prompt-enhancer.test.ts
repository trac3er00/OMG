import { describe, expect, test } from "bun:test";
import { BUDGET_PROMPT_TOTAL } from "../hooks/_budget.ts";
import { run, tempDir } from "./helpers.ts";

describe("prompt enhancer", () => {
  test("simple greetings produce no output", () => {
    const dir = tempDir("omg-prompt-");
    const proc = run(["bun", "hooks/prompt-enhancer.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({ user_message: "hello" })
    });
    expect(proc.stdout.toString().trim()).toBe("");
  });

  test("keyword prompts produce bounded injections", () => {
    const dir = tempDir("omg-prompt-key-");
    const proc = run(["bun", "hooks/prompt-enhancer.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({ user_message: "fix the bug in the auth module and implement error handling" })
    });
    const payload = JSON.parse(proc.stdout.toString());
    expect(payload.contextInjection.length).toBeLessThanOrEqual(BUDGET_PROMPT_TOTAL);
    expect(payload.contextInjection).toContain("OMG Bun runtime context");
  });
});
