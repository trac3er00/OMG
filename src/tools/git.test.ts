import { describe, expect, test } from "bun:test";
import { CommitSplitter, GitInspector } from "./git.js";

describe("GitInspector", () => {
  const inspector = new GitInspector(".");

  test("getStatus returns structured data", async () => {
    const status = await inspector.getStatus();
    expect(Array.isArray(status.staged)).toBe(true);
    expect(Array.isArray(status.unstaged)).toBe(true);
    expect(Array.isArray(status.untracked)).toBe(true);
    expect(typeof status.branch).toBe("string");
    expect(status.branch.length).toBeGreaterThan(0);
  });

  test("getDiff returns a string", async () => {
    const diff = await inspector.getDiff();
    expect(typeof diff).toBe("string");
  });

  test("getLog returns commit entries", async () => {
    const commits = await inspector.getLog(5);
    expect(Array.isArray(commits)).toBe(true);
    if (commits.length > 0) {
      const first = commits[0];
      expect(first).toBeDefined();
      expect(typeof first?.hash).toBe("string");
      expect(typeof first?.subject).toBe("string");
      expect(typeof first?.author).toBe("string");
      expect(typeof first?.date).toBe("string");
      expect(first?.hash.length).toBe(40);
    }
  });

  test("getBranch returns current branch name", async () => {
    const branch = await inspector.getBranch();
    expect(typeof branch).toBe("string");
    expect(branch.length).toBeGreaterThan(0);
    expect(branch).not.toBe("unknown");
  });
});

describe("CommitSplitter", () => {
  const splitter = new CommitSplitter();

  const SAMPLE_DIFF = [
    "diff --git a/src/foo.ts b/src/foo.ts",
    "index abc1234..def5678 100644",
    "--- a/src/foo.ts",
    "+++ b/src/foo.ts",
    "@@ -1,3 +1,4 @@",
    " import { bar } from './bar';",
    "+import { baz } from './baz';",
    " ",
    " export function foo() {",
    "diff --git a/src/bar.ts b/src/bar.ts",
    "index 1111111..2222222 100644",
    "--- a/src/bar.ts",
    "+++ b/src/bar.ts",
    "@@ -10,6 +10,8 @@ export function bar() {",
    "   const x = 1;",
    "+  const y = 2;",
    "+  const z = 3;",
    "   return x;",
  ].join("\n");

  test("splitByFile groups diff by file", () => {
    const splits = splitter.splitByFile(SAMPLE_DIFF);
    expect(splits).toHaveLength(2);
    expect(splits[0]?.file).toBe("src/foo.ts");
    expect(splits[1]?.file).toBe("src/bar.ts");
    expect(splits[0]?.content).toContain("import { baz }");
    expect(splits[1]?.content).toContain("const y = 2");
  });

  test("splitByHunk parses hunk headers and lines", () => {
    const hunks = splitter.splitByHunk(SAMPLE_DIFF);
    expect(hunks).toHaveLength(2);

    const firstHunk = hunks[0];
    expect(firstHunk).toBeDefined();
    expect(firstHunk?.file).toBe("src/foo.ts");
    expect(firstHunk?.oldStart).toBe(1);
    expect(firstHunk?.oldCount).toBe(3);
    expect(firstHunk?.newStart).toBe(1);
    expect(firstHunk?.newCount).toBe(4);
    expect(firstHunk?.lines.some((l) => l.includes("baz"))).toBe(true);

    const secondHunk = hunks[1];
    expect(secondHunk).toBeDefined();
    expect(secondHunk?.file).toBe("src/bar.ts");
    expect(secondHunk?.oldStart).toBe(10);
    expect(secondHunk?.oldCount).toBe(6);
    expect(secondHunk?.newStart).toBe(10);
    expect(secondHunk?.newCount).toBe(8);
    expect(secondHunk?.context).toBe("export function bar() {");
  });

  test("splitByFile returns empty for empty diff", () => {
    expect(splitter.splitByFile("")).toHaveLength(0);
  });

  test("splitByHunk returns empty for empty diff", () => {
    expect(splitter.splitByHunk("")).toHaveLength(0);
  });

  test("splitByHunk handles single-line hunk header without count", () => {
    const diff = [
      "diff --git a/x.ts b/x.ts",
      "--- a/x.ts",
      "+++ b/x.ts",
      "@@ -1 +1,2 @@",
      " old line",
      "+new line",
    ].join("\n");

    const hunks = splitter.splitByHunk(diff);
    expect(hunks).toHaveLength(1);
    expect(hunks[0]?.oldCount).toBe(1);
    expect(hunks[0]?.newCount).toBe(2);
  });
});
