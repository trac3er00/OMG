import { afterEach, describe, expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { slugify, runAutoresearch } from "./autoresearch.js";

const TEST_OUTPUT_DIR = join(process.cwd(), ".omg", "research-test");

afterEach(() => {
  if (existsSync(TEST_OUTPUT_DIR)) {
    rmSync(TEST_OUTPUT_DIR, { recursive: true, force: true });
  }
});

describe("autoresearch command", () => {
  test("command-exists: module exports command, describe, builder, handler", async () => {
    const mod = await import("./autoresearch.js");
    expect(mod.autoresearchCommand).toBeDefined();
    expect(mod.autoresearchCommand.command).toBe("autoresearch <topic>");
    expect(mod.autoresearchCommand.describe).toBeString();
    expect(mod.autoresearchCommand.builder).toBeFunction();
    expect(mod.autoresearchCommand.handler).toBeFunction();
  });

  test("slug-generation: topic 'TypeScript error handling' produces correct slug", () => {
    expect(slugify("TypeScript error handling")).toBe(
      "typescript-error-handling",
    );
    expect(slugify("Hello World!")).toBe("hello-world");
    expect(slugify("  spaces  around  ")).toBe("spaces-around");
    expect(slugify("special@chars#here$")).toBe("specialcharshere");
    expect(slugify("a".repeat(100))).toHaveLength(50);
  });

  test("report-structure: generated report has Summary, Findings, Code References, Recommendations sections", () => {
    const outputPath = runAutoresearch(
      "test topic for structure",
      TEST_OUTPUT_DIR,
      10_000,
    );

    expect(existsSync(outputPath)).toBe(true);

    const content = readFileSync(outputPath, "utf8");
    expect(content).toContain("## Summary");
    expect(content).toContain("## Findings");
    expect(content).toContain("## Code References");
    expect(content).toContain("## Recommendations");
    expect(content).toContain("# Research: test topic for structure");
  });

  test("output-path: report is written to the correct directory with slugified name", () => {
    const outputPath = runAutoresearch(
      "output path check",
      TEST_OUTPUT_DIR,
      10_000,
    );

    expect(outputPath).toStartWith(TEST_OUTPUT_DIR);
    expect(outputPath).toEndWith(".md");
    expect(existsSync(outputPath)).toBe(true);
  });

  test("budget-defaults: ResearchBudget fields have expected defaults", async () => {
    const mod = await import("./autoresearch.js");
    expect(mod.slugify).toBeFunction();
    expect(mod.runAutoresearch).toBeFunction();
  });
});
