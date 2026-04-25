import { afterEach, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  FidelityChecker,
  checkFidelity,
  shouldClarify,
} from "./fidelity-checker.js";

const ORIGINAL_CWD = process.cwd();

function withTempCwd<T>(run: (dir: string) => T): T {
  const dir = mkdtempSync(join(tmpdir(), "fidelity-checker-"));
  process.chdir(dir);

  try {
    return run(dir);
  } finally {
    process.chdir(ORIGINAL_CWD);
    rmSync(dir, { recursive: true, force: true });
  }
}

afterEach(() => {
  process.chdir(ORIGINAL_CWD);
});

test("requests clarification for ambiguous goals", () => {
  withTempCwd(() => {
    const result = checkFidelity({ goal: "build something" });

    expect(result.needsClarification).toBe(true);
    expect(result.canProceed).toBe(false);
    expect(result.clarificationQuestion).toBeTruthy();
    expect(result.gapChecks).toHaveLength(3);
    expect(result.interpretation).toContain("build request");
  });
});

test("passes clear goals without clarification", () => {
  const result = checkFidelity({ goal: "make a landing page for my SaaS" });

  expect(result.needsClarification).toBe(false);
  expect(result.clarificationQuestion).toBeNull();
  expect(result.canProceed).toBe(true);
  expect(shouldClarify("make a landing page for my SaaS")).toBe(false);
});

test("proceeds after max 3 clarification rounds", () => {
  withTempCwd(() => {
    const result = checkFidelity({
      goal: "build something",
      history: ["round 1", "round 2", "round 3"],
      round: 3,
    });

    expect(result.round).toBe(3);
    expect(result.needsClarification).toBe(false);
    expect(result.clarificationQuestion).toBeNull();
    expect(result.canProceed).toBe(true);
  });
});

test("generates exactly one question per round", () => {
  withTempCwd(() => {
    const checker = new FidelityChecker();
    const result = checker.check({ goal: "build something" });

    expect(result.clarificationQuestion).not.toBeNull();
    expect(result.clarificationQuestion!.match(/\?/gu)).toHaveLength(1);
    expect(result.clarificationQuestion).not.toContain("\n");
  });
});

test("logs intent gaps when clarification needed", () => {
  withTempCwd((dir) => {
    const result = checkFidelity({ goal: "build something" });
    const logPath = join(dir, ".omg", "intent", "gaps.jsonl");

    expect(result.needsClarification).toBe(true);
    expect(existsSync(logPath)).toBe(true);

    const lines = readFileSync(logPath, "utf8").trim().split("\n");
    const entry = JSON.parse(lines.at(-1) ?? "{}");

    expect(entry.goal).toBe("build something");
    expect(entry.clarificationQuestion).toBe(result.clarificationQuestion);
    expect(entry.gapChecks).toHaveLength(3);
  });
});

test("trivial requests skip clarification", () => {
  const result = checkFidelity({ goal: "fix typo" });

  expect(result.needsClarification).toBe(false);
  expect(result.clarificationQuestion).toBeNull();
  expect(result.canProceed).toBe(true);
  expect(shouldClarify("fix typo")).toBe(false);
});

test("advances to the next significant gap on later rounds", () => {
  withTempCwd(() => {
    const firstRound = checkFidelity({ goal: "build something", round: 0 });
    const secondRound = checkFidelity({ goal: "build something", round: 1 });

    expect(firstRound.clarificationQuestion).not.toBeNull();
    expect(secondRound.clarificationQuestion).not.toBeNull();
    expect(secondRound.clarificationQuestion).not.toBe(
      firstRound.clarificationQuestion,
    );
  });
});
