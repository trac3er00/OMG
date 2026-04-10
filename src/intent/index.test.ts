import { expect, test } from "bun:test";
import { createUserSessionServices } from "../state/uss.js";
import { understandIntent } from "./index.js";

const CASES = [
  {
    prompt: "fix typo in login button",
    intent: "trivial",
    domain: "frontend",
  },
  {
    prompt: "redesign auth system",
    intent: "architectural",
    domain: "security",
  },
  {
    prompt: "add pagination to the admin dashboard table",
    intent: "moderate",
    domain: "frontend",
  },
  {
    prompt: "implement webhook retry handling for failed payment events",
    intent: "moderate",
    domain: "backend",
  },
  {
    prompt: "compare bun and node startup time for the cli",
    intent: "research",
    domain: "other",
  },
  {
    prompt: "migrate analytics pipeline to a new warehouse",
    intent: "complex",
    domain: "data",
  },
  {
    prompt: "update kubernetes deployment for blue green rollout",
    intent: "simple",
    domain: "infrastructure",
  },
  {
    prompt: "write readme guide for local development setup",
    intent: "simple",
    domain: "documentation",
  },
  {
    prompt: "build oauth token rotation workflow",
    intent: "moderate",
    domain: "security",
  },
  {
    prompt: "refactor the database schema migration helper",
    intent: "moderate",
    domain: "data",
  },
] as const;

for (const entry of CASES) {
  test(`classifies: ${entry.prompt}`, () => {
    const result = understandIntent(entry.prompt);
    expect(result.intent).toBe(entry.intent);
    expect(result.domain).toBe(entry.domain);
  });
}

test("detects ambiguity and asks clarifying questions", () => {
  const result = understandIntent("do something with the API");

  expect(result.ambiguities.length).toBeGreaterThan(0);
  expect(result.clarifyingQuestions.length).toBeGreaterThan(0);
  expect(result.clarifyingQuestions).toContain(
    "Which API endpoint or contract should be updated, and how should its behavior change?",
  );
  expect(result.suggestedApproach).toContain(
    "Resolve the ambiguities before implementation",
  );
});

test("USS profile influences suggested approach", () => {
  const beginner = createUserSessionServices();
  beginner.setPreference("technicalLevel", "beginner");
  beginner.setPreference("language", "en");
  beginner.setPreference("namingConvention", "snake_case");

  const advanced = createUserSessionServices();
  advanced.setPreference("technicalLevel", "advanced");
  advanced.setPreference("language", "ko");
  advanced.setPreference("namingConvention", "camelCase");

  const beginnerResult = understandIntent(
    "implement webhook retry handling for failed payment events",
    { uss: beginner },
  );
  const advancedResult = understandIntent(
    "implement webhook retry handling for failed payment events",
    { uss: advanced },
  );

  expect(beginnerResult.suggestedApproach).toContain(
    "Prefer a step-by-step explanation with minimal jargon.",
  );
  expect(beginnerResult.suggestedApproach).toContain(
    "prefer snake_case naming",
  );
  expect(advancedResult.suggestedApproach).toContain(
    "Emphasize tradeoffs, constraints, and optimization opportunities.",
  );
  expect(advancedResult.suggestedApproach).toContain("한국어로 설명하고");
});
