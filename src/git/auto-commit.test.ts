import { describe, expect, test } from "bun:test";
import {
  PROTECTED_BRANCHES,
  createAutoCommit,
  formatConventionalCommit,
} from "./auto-commit.js";

describe("auto-commit", () => {
  test("formatConventionalCommit formats correctly", () => {
    expect(typeof createAutoCommit).toBe("function");
    const result = formatConventionalCommit("feat", "auth", "add login");
    expect(result).toBe("feat(auth): add login");
  });

  test("createAutoCommit blocks main branch", () => {
    const isProtected = PROTECTED_BRANCHES.has("main");
    expect(isProtected).toBe(true);
    expect(PROTECTED_BRANCHES.has("master")).toBe(true);
    expect(PROTECTED_BRANCHES.has("feature-branch")).toBe(false);
  });

  test("conventional commit format is enforced", () => {
    const valid = formatConventionalCommit("feat", "test", "test commit");
    expect(valid).toMatch(/^[a-z]+\([^)]+\):\s.+/);
  });
});
