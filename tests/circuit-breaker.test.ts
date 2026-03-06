import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { run, tempDir } from "./helpers.ts";

function trackerPath(projectDir: string): string {
  return join(projectDir, ".omg", "state", "ledger", "failure-tracker.json");
}

function readTracker(projectDir: string) {
  return existsSync(trackerPath(projectDir)) ? JSON.parse(readFileSync(trackerPath(projectDir), "utf8")) : {};
}

describe("circuit breaker hook", () => {
  test("creates tracker entry on failure and clears on success", () => {
    const dir = tempDir("omg-cb-");
    mkdirSync(join(dir, ".omg", "state", "ledger"), { recursive: true });
    const fail = run(["bun", "hooks/circuit-breaker.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({
        tool_name: "Bash",
        tool_input: { command: "npm run test" },
        tool_response: { exitCode: 1, stderr: "fail" }
      })
    });
    expect(fail.exitCode).toBe(0);
    const tracker = readTracker(dir);
    expect(tracker["Bash:npm test"].count).toBe(1);

    const success = run(["bun", "hooks/circuit-breaker.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({
        tool_name: "Bash",
        tool_input: { command: "npm test" },
        tool_response: { exitCode: 0 }
      })
    });
    expect(success.exitCode).toBe(0);
    expect(readTracker(dir)["Bash:npm test"]).toBeUndefined();
  });

  test("emits warning and escalation thresholds", () => {
    const dir = tempDir("omg-cb-threshold-");
    mkdirSync(join(dir, ".omg", "state", "ledger"), { recursive: true });
    writeFileSync(
      trackerPath(dir),
      JSON.stringify({
        "Bash:npm test": {
          count: 2,
          last_failure: new Date().toISOString(),
          errors: ["a", "b"]
        }
      })
    );
    const warning = run(["bun", "hooks/circuit-breaker.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({
        tool_name: "Bash",
        tool_input: { command: "npm test" },
        tool_response: { exitCode: 1, stderr: "c" }
      })
    });
    expect(warning.stderr.toString()).toContain("CIRCUIT BREAKER WARNING");

    writeFileSync(
      trackerPath(dir),
      JSON.stringify({
        "Bash:npm test": {
          count: 4,
          last_failure: new Date().toISOString(),
          errors: ["a", "b", "c"]
        }
      })
    );
    const escalation = run(["bun", "hooks/circuit-breaker.ts"], {
      env: { CLAUDE_PROJECT_DIR: dir },
      stdin: JSON.stringify({
        tool_name: "Bash",
        tool_input: { command: "npm test" },
        tool_response: { exitCode: 1, stderr: "d" }
      })
    });
    expect(escalation.stderr.toString()).toContain("CIRCUIT BREAKER ESCALATE");
  });
});
