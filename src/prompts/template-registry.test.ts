import { describe, test, expect, beforeEach } from "bun:test";
import {
  PROMPTS_VERSION,
  registerTemplate,
  getTemplate,
  listTaskTypes,
  buildPrompt,
  clearTemplateRegistry,
  PromptTemplateSchema,
  type PromptTemplate,
} from "./template-registry.js";

function makeTemplate(
  taskType: PromptTemplate["task_type"],
  version = "1.0.0",
): PromptTemplate {
  return PromptTemplateSchema.parse({
    template_id: `${taskType}-${version}`,
    task_type: taskType,
    version,
    content: `Review the {{code}} for ${taskType} concerns.`,
    few_shot_examples: [],
    chain_of_thought: false,
    created_at: new Date().toISOString(),
  });
}

beforeEach(() => clearTemplateRegistry());

describe("prompts/template-registry", () => {
  test("PROMPTS_VERSION is 1.0.0", () => {
    expect(PROMPTS_VERSION).toBe("1.0.0");
  });

  describe("registerTemplate", () => {
    test("registers template successfully", () => {
      registerTemplate(makeTemplate("code-review"));
      expect(getTemplate("code-review")).not.toBeNull();
    });

    test("registers multiple versions", () => {
      registerTemplate(makeTemplate("code-review", "1.0.0"));
      registerTemplate(makeTemplate("code-review", "1.1.0"));
      expect(getTemplate("code-review", "1.0.0")).not.toBeNull();
      expect(getTemplate("code-review", "1.1.0")).not.toBeNull();
    });
  });

  describe("getTemplate", () => {
    test("returns null for missing template", () => {
      expect(getTemplate("security-audit")).toBeNull();
    });

    test("returns specific version when requested", () => {
      registerTemplate(makeTemplate("code-review", "1.0.0"));
      registerTemplate(makeTemplate("code-review", "1.1.0"));
      const result = getTemplate("code-review", "1.0.0");
      expect(result?.version).toBe("1.0.0");
    });

    test("returns latest when no version specified", () => {
      registerTemplate(makeTemplate("code-review", "1.0.0"));
      registerTemplate(makeTemplate("code-review", "1.1.0"));
      const result = getTemplate("code-review");
      expect(result?.version).toBe("1.1.0");
    });

    test("returns null for unknown version", () => {
      registerTemplate(makeTemplate("code-review", "1.0.0"));
      expect(getTemplate("code-review", "9.9.9")).toBeNull();
    });
  });

  describe("buildPrompt", () => {
    test("substitutes template variables", () => {
      const template = makeTemplate("code-review");
      const prompt = buildPrompt(template, { code: "function foo() {}" });
      expect(prompt).toContain("function foo() {}");
      expect(prompt).not.toContain("{{code}}");
    });

    test("appends CoT instruction when enabled", () => {
      const template = {
        ...makeTemplate("code-review"),
        chain_of_thought: true,
      };
      const prompt = buildPrompt(template, { code: "test" });
      expect(prompt).toContain("step by step");
    });
  });

  describe("listTaskTypes", () => {
    test("returns empty array when empty", () => {
      expect(listTaskTypes()).toEqual([]);
    });

    test("lists registered task types", () => {
      registerTemplate(makeTemplate("code-review"));
      registerTemplate(makeTemplate("security-audit"));
      const types = listTaskTypes();
      expect(types).toContain("code-review");
      expect(types).toContain("security-audit");
    });
  });
});
