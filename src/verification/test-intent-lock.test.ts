import { describe, test, expect, afterEach } from "bun:test";
import {
  TestIntentLock,
  resolveTestFile,
  type TestEvidence,
} from "./test-intent-lock.js";
import {
  classifyBashCommand,
  checkCommandCompliance,
  classifyBashCommandMode,
} from "./compliance-governor.js";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync } from "node:fs";

describe("TestIntentLock", () => {
  const dirs: string[] = [];

  function mkLock(): { lock: TestIntentLock; dir: string } {
    const dir = join(tmpdir(), `tlock-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    dirs.push(dir);
    return { lock: new TestIntentLock(dir), dir };
  }

  afterEach(() => {
    for (const d of dirs) {
      rmSync(d, { recursive: true, force: true });
    }
    dirs.length = 0;
  });

  test("initially unlocked", () => {
    const { lock } = mkLock();
    expect(lock.isLocked()).toBe(false);
  });

  test("acquire sets locked state", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    expect(lock.isLocked()).toBe(true);
  });

  test("release clears locked state", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    lock.release("omg-run-001");
    expect(lock.isLocked()).toBe(false);
  });

  test("release with wrong runId is a no-op", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    lock.release("wrong-id");
    expect(lock.isLocked()).toBe(true);
    lock.release("omg-run-001");
  });

  test("write blocked when locked — no test evidence", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    const result = lock.checkWriteAllowed("src/feature.ts", []);
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("No test evidence");
    lock.release("omg-run-001");
  });

  test("write allowed when locked — passing test evidence", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    const evidence: readonly TestEvidence[] = [
      { file: "src/feature.test.ts", passed: true },
    ];
    const result = lock.checkWriteAllowed("src/feature.ts", evidence);
    expect(result.allowed).toBe(true);
    expect(result.reason).toContain("Passing test evidence");
    lock.release("omg-run-001");
  });

  test("write blocked when locked — failing test evidence", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    const evidence: readonly TestEvidence[] = [
      { file: "src/feature.test.ts", passed: false },
    ];
    const result = lock.checkWriteAllowed("src/feature.ts", evidence);
    expect(result.allowed).toBe(false);
    expect(result.reason).toContain("failing");
    lock.release("omg-run-001");
  });

  test("write allowed when unlocked — no enforcement", () => {
    const { lock } = mkLock();
    const result = lock.checkWriteAllowed("src/feature.ts", []);
    expect(result.allowed).toBe(true);
    expect(result.reason).toContain("not active");
  });

  test("evidence matched by stem (partial filename)", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    const evidence: readonly TestEvidence[] = [
      { file: "tests/feature.spec.ts", passed: true },
    ];
    const result = lock.checkWriteAllowed("src/feature.ts", evidence);
    expect(result.allowed).toBe(true);
    lock.release("omg-run-001");
  });

  test("lockState returns full state snapshot", () => {
    const { lock } = mkLock();
    lock.acquire("omg-run-001");
    const state = lock.lockState();
    expect(state.locked).toBe(true);
    expect(state.runId).toBe("omg-run-001");
    expect(state.lockedAt).toBeDefined();
    lock.release("omg-run-001");
  });
});

describe("resolveTestFile", () => {
  test("src/foo.ts -> src/foo.test.ts", () => {
    expect(resolveTestFile("src/foo.ts")).toBe("src/foo.test.ts");
  });

  test("src/bar.js -> src/bar.test.js", () => {
    expect(resolveTestFile("src/bar.js")).toBe("src/bar.test.js");
  });

  test("src/baz.tsx -> src/baz.test.tsx", () => {
    expect(resolveTestFile("src/baz.tsx")).toBe("src/baz.test.tsx");
  });

  test("src/qux.jsx -> src/qux.test.jsx", () => {
    expect(resolveTestFile("src/qux.jsx")).toBe("src/qux.test.jsx");
  });

  test("already a test file -> double .test suffix", () => {
    expect(resolveTestFile("src/foo.test.ts")).toBe("src/foo.test.test.ts");
  });
});

describe("classifyBashCommand", () => {
  test("bun test -> test", () => {
    expect(classifyBashCommand("bun test src/")).toBe("test");
  });

  test("pytest -> test", () => {
    expect(classifyBashCommand("pytest tests/")).toBe("test");
  });

  test("npm test -> test", () => {
    expect(classifyBashCommand("npm test")).toBe("test");
  });

  test("git commit -> vcs", () => {
    expect(classifyBashCommand("git commit -m 'fix'")).toBe("vcs");
  });

  test("git push -> vcs", () => {
    expect(classifyBashCommand("git push origin main")).toBe("vcs");
  });

  test("ls -la -> read", () => {
    expect(classifyBashCommand("ls -la")).toBe("read");
  });

  test("grep pattern -> read", () => {
    expect(classifyBashCommand("grep -r 'foo' src/")).toBe("read");
  });

  test("rm -rf -> destructive", () => {
    expect(classifyBashCommand("rm -rf /")).toBe("destructive");
  });

  test("curl -> network", () => {
    expect(classifyBashCommand("curl https://example.com")).toBe("network");
  });

  test("npm install -> network", () => {
    expect(classifyBashCommand("npm install lodash")).toBe("network");
  });

  test("tsc --build -> build", () => {
    expect(classifyBashCommand("tsc --build")).toBe("build");
  });

  test("bun build -> build", () => {
    expect(classifyBashCommand("bun build src/index.ts")).toBe("build");
  });

  test("echo hello -> write", () => {
    expect(classifyBashCommand("echo hello")).toBe("write");
  });

  test("empty string -> unknown", () => {
    expect(classifyBashCommand("")).toBe("unknown");
  });

  test("random command -> unknown", () => {
    expect(classifyBashCommand("my-custom-tool --flag")).toBe("unknown");
  });
});

describe("checkCommandCompliance", () => {
  test("read command -> allowed", () => {
    const result = checkCommandCompliance("ls -la");
    expect(result.allowed).toBe(true);
    expect(result.commandClass).toBe("read");
  });

  test("destructive command -> blocked", () => {
    const result = checkCommandCompliance("rm -rf /tmp/data");
    expect(result.allowed).toBe(false);
    expect(result.commandClass).toBe("destructive");
    expect(result.reason).toContain("Destructive");
  });

  test("test command -> allowed", () => {
    const result = checkCommandCompliance("bun test src/");
    expect(result.allowed).toBe(true);
    expect(result.commandClass).toBe("test");
  });
});

describe("classifyBashCommandMode", () => {
  test("empty -> read", () => {
    expect(classifyBashCommandMode("")).toBe("read");
  });

  test("git commit -> mutation", () => {
    expect(classifyBashCommandMode("git commit -m 'msg'")).toBe("mutation");
  });

  test("curl -> external", () => {
    expect(classifyBashCommandMode("curl https://api.example.com")).toBe("external");
  });

  test("ls -> read", () => {
    expect(classifyBashCommandMode("ls -la")).toBe("read");
  });

  test("rm file -> mutation", () => {
    expect(classifyBashCommandMode("rm file.txt")).toBe("mutation");
  });

  test("ssh -> external", () => {
    expect(classifyBashCommandMode("ssh user@host")).toBe("external");
  });

  test("git fetch -> external", () => {
    expect(classifyBashCommandMode("git fetch origin")).toBe("external");
  });
});
