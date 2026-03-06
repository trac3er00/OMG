import { describe, expect, test } from "bun:test";
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR, run, stdoutJson, tempDir } from "./helpers.ts";

describe("omg cli", () => {
  test("runtime dispatch inline json", () => {
    const proc = run(["bun", "scripts/omg.ts", "runtime", "dispatch", "--runtime", "claude", "--idea-json", '{"goal":"x"}']);
    expect(proc.exitCode).toBe(0);
    const out = stdoutJson(proc);
    expect(out.status).toBe("ok");
    expect(out.runtime).toBe("claude");
  });

  test("trust review denies dangerous permission changes", () => {
    const dir = tempDir("omg-trust-");
    const oldPath = join(dir, "old.json");
    const newPath = join(dir, "new.json");
    writeFileSync(oldPath, JSON.stringify({ permissions: { allow: ["Read"] } }));
    writeFileSync(newPath, JSON.stringify({ permissions: { allow: ["Read", "Bash(sudo:*)"] } }));
    const proc = run(["bun", "scripts/omg.ts", "trust", "review", "--old", oldPath, "--new", newPath], {
      env: { CLAUDE_PROJECT_DIR: dir }
    });
    expect(proc.exitCode).toBe(0);
    const out = stdoutJson(proc);
    expect(out.review.verdict).toBe("deny");
    expect(out.review.risk_level).toBe("critical");
  });

  test("teams auto routing honors explicit and mixed keywords", () => {
    const gemini = run(["bun", "scripts/omg.ts", "teams", "--target", "auto", "--problem", "please use gemini for this component"]);
    expect(gemini.exitCode).toBe(0);
    expect(stdoutJson(gemini).evidence.target).toBe("gemini");

    const ccg = run([
      "bun",
      "scripts/omg.ts",
      "teams",
      "--target",
      "auto",
      "--problem",
      "run a ccg review for full stack auth and dashboard"
    ]);
    expect(ccg.exitCode).toBe(0);
    expect(stdoutJson(ccg).evidence.target).toBe("ccg");
  });

  test("ccg and crazy preserve worker contracts", () => {
    const ccg = stdoutJson(run(["bun", "scripts/omg.ts", "ccg", "--problem", "review full stack architecture"]));
    expect(ccg.worker_count).toBe(2);
    expect(ccg.parallel_execution).toBe(true);

    const crazy = stdoutJson(run(["bun", "scripts/omg.ts", "crazy", "--problem", "stabilize auth and dashboard flows"]));
    expect(crazy.worker_count).toBe(5);
    expect(crazy.sequential_execution).toBe(false);
  });

  test("compat list, run, snapshot, and gate work", () => {
    const dir = tempDir("omg-compat-");
    const list = stdoutJson(run(["bun", "scripts/omg.ts", "compat", "list"]));
    expect(list.count).toBeGreaterThanOrEqual(30);
    expect(list.skills).toContain("omg-teams");

    const runResult = stdoutJson(
      run(["bun", "scripts/omg.ts", "compat", "run", "--skill", "omg-teams", "--problem", "compat smoke"], {
        env: { CLAUDE_PROJECT_DIR: dir }
      })
    );
    expect(runResult.schema).toBe("OmgCompatResult");
    expect(runResult.status).toBe("ok");

    const snapshotPath = join(dir, "contracts.json");
    const snapshot = stdoutJson(
      run(["bun", "scripts/omg.ts", "compat", "snapshot", "--output", snapshotPath], {
        env: { CLAUDE_PROJECT_DIR: dir }
      })
    );
    expect(snapshot.count).toBeGreaterThanOrEqual(30);
    expect(existsSync(snapshotPath)).toBe(true);

    const gatePath = join(dir, "gap.json");
    const gate = stdoutJson(
      run(["bun", "scripts/omg.ts", "compat", "gate", "--max-bridge", "0", "--output", gatePath], {
        env: { CLAUDE_PROJECT_DIR: dir }
      })
    );
    expect(gate.status).toBe("ok");
    expect(existsSync(gatePath)).toBe(true);
  });

  test("ecosystem list, status, and noop sync work", () => {
    const dir = tempDir("omg-ecosystem-");
    const list = stdoutJson(run(["bun", "scripts/omg.ts", "ecosystem", "list"], { env: { CLAUDE_PROJECT_DIR: dir } }));
    expect(list.count).toBeGreaterThanOrEqual(9);

    const status = stdoutJson(run(["bun", "scripts/omg.ts", "ecosystem", "status"], { env: { CLAUDE_PROJECT_DIR: dir } }));
    expect(status.status).toBe("ok");

    const sync = stdoutJson(
      run(["bun", "scripts/omg.ts", "ecosystem", "sync", "--names", "unknown-plugin"], { env: { CLAUDE_PROJECT_DIR: dir } })
    );
    expect(sync.status).toBe("ok");
    expect(sync.unknown).toEqual(["unknown-plugin"]);
  });

  test("providers and release readiness return json", () => {
    const status = stdoutJson(run(["bun", "scripts/omg.ts", "providers", "status", "--smoke"]));
    expect(status.status).toBe("ok");
    expect(status.providers.length).toBe(4);

    const readiness = stdoutJson(run(["bun", "scripts/omg.ts", "release", "readiness"]));
    expect(readiness.status).toBe("ok");
    expect(typeof readiness.git.branch).toBe("string");
  });
});
