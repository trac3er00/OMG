import { describe, expect, test } from "bun:test";
import { PersonalizationEngine } from "./unique-output.js";

describe("PersonalizationEngine", () => {
  test("produces different output for different user profiles on the same prompt", () => {
    const engine = new PersonalizationEngine();
    const prompt = "Build a reusable dashboard component for task management";

    const profileA = {
      language: "ko",
      framework: "react",
      codingStyle: "functional",
      techLevel: "advanced",
      namingConvention: "camelCase",
      stack: ["react", "typescript"],
    } as const;

    const profileB = {
      language: "en",
      framework: "vue",
      codingStyle: "class-based",
      techLevel: "intermediate",
      namingConvention: "snake_case",
      stack: ["vue", "typescript"],
    } as const;

    const koreanReact = engine.generate(prompt, profileA);
    const englishVue = engine.generate(prompt, profileB);

    expect(koreanReact.content).not.toBe(englishVue.content);
    expect(koreanReact.profile.framework).toBe("react");
    expect(englishVue.profile.framework).toBe("vue");
  });

  test("reflects framework, language, and coding style preferences", () => {
    const engine = new PersonalizationEngine();

    const reactOutput = engine.generate("Create a settings page", {
      language: "ko",
      framework: "react",
      codingStyle: "functional",
      techLevel: "advanced",
      namingConvention: "camelCase",
    });

    expect(reactOutput.content).toContain("React 함수형 컴포넌트");
    expect(reactOutput.content).toContain("한국어");
    expect(reactOutput.content).toContain("camelCase");

    const vueOutput = engine.generate("Create a settings page", {
      language: "en",
      framework: "vue",
      codingStyle: "class-based",
      techLevel: "intermediate",
      namingConvention: "snake_case",
    });

    expect(vueOutput.content).toContain("Vue class-style components");
    expect(vueOutput.content).toContain("snake_case");
    expect(vueOutput.content).toContain("class-based");
  });

  test("accepts USS-shaped profiles and infers the framework from stack", () => {
    const engine = new PersonalizationEngine();
    const output = engine.generate("Implement auth UI", {
      language: "en",
      technicalLevel: "beginner",
      namingConvention: "camelCase",
      stack: ["react", "typescript"],
    });

    expect(output.profile.framework).toBe("react");
    expect(output.content).toContain("React function components and hooks");
    expect(output.content).toContain("beginner");
  });
});
