import { describe, test, expect } from "bun:test";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const SKILL_PATH = resolve(
  import.meta.dir,
  "../../.agents/skills/omg/plan-council/SKILL.md",
);

describe("skills/plan-council", () => {
  test("SKILL.md exists", () => {
    expect(existsSync(SKILL_PATH)).toBe(true);
  });

  test("SKILL.md is non-empty", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content.length).toBeGreaterThan(0);
  });

  test("has valid YAML frontmatter with name and description", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content).toMatch(/^---\n/);
    expect(content).toMatch(/name:\s+omg-plan-council/);
    expect(content).toMatch(/description:\s+".+"/);
  });

  test("has council-related heading", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content).toMatch(/# OMG Plan Council/);
  });

  test("references evidence outputs", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content).toContain(".omg/evidence/plan-council.json");
  });

  test("specifies execution modes", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content).toMatch(/Execution modes:/);
  });

  test("references omg-control MCP server", () => {
    const content = readFileSync(SKILL_PATH, "utf-8");
    expect(content).toContain("omg-control");
  });
});
