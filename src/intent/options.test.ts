import { expect, test } from "bun:test";
import { understandIntent } from "./index.js";
import { generate131Options, resolveDecisionPoint } from "./options.js";

test("ambiguous auth task generates exactly 3 options with 1 recommended", () => {
  const analysis = understandIntent("set up auth for my app");
  const result = resolveDecisionPoint(analysis);

  expect(result).not.toBeNull();
  expect(result!.options).toHaveLength(3);
  expect(result!.options.filter((o) => o.recommended)).toHaveLength(1);
  expect(result!.problem).toBeTruthy();

  for (const option of result!.options) {
    expect(option.label).toBeTruthy();
    expect(option.description).toBeTruthy();
    expect(option.tradeoffs.pros.length).toBeGreaterThan(0);
    expect(option.tradeoffs.cons.length).toBeGreaterThan(0);
  }
});

test("clear trivial task generates no options", () => {
  const analysis = understandIntent("fix typo");
  const result = resolveDecisionPoint(analysis);

  expect(result).toBeNull();
});

test("each option has non-empty tradeoffs with specific content", () => {
  const analysis = understandIntent("set up auth for my app");
  const result = resolveDecisionPoint(analysis);

  expect(result).not.toBeNull();
  for (const option of result!.options) {
    for (const pro of option.tradeoffs.pros) {
      expect(pro.length).toBeGreaterThan(10);
    }
    for (const con of option.tradeoffs.cons) {
      expect(con.length).toBeGreaterThan(10);
    }
  }
});

test("generate131Options uses explicit ambiguity as problem", () => {
  const analysis = understandIntent("set up auth for my app");
  const result = generate131Options(
    "Multiple auth strategies are viable",
    analysis,
  );

  expect(result.problem).toBe("Multiple auth strategies are viable");
  expect(result.options).toHaveLength(3);
  expect(result.options.filter((o) => o.recommended)).toHaveLength(1);
});

test("exactly one option is recommended per set", () => {
  const prompts = [
    "deploy the service to production",
    "implement user API",
    "create a dashboard component",
    "migrate the analytics schema",
  ];

  for (const prompt of prompts) {
    const analysis = understandIntent(prompt);
    const result = resolveDecisionPoint(analysis);
    if (result) {
      const recommended = result.options.filter((o) => o.recommended);
      expect(recommended).toHaveLength(1);
      expect(result.options).toHaveLength(3);
    }
  }
});

test("clear simple documentation task proceeds directly", () => {
  const analysis = understandIntent("fix typo in login button");
  const result = resolveDecisionPoint(analysis);

  expect(result).toBeNull();
});

test("infrastructure domain triggers decision point", () => {
  const analysis = understandIntent("deploy the service to kubernetes");
  const result = resolveDecisionPoint(analysis);

  expect(result).not.toBeNull();
  expect(result!.options).toHaveLength(3);
  expect(result!.options.filter((o) => o.recommended)).toHaveLength(1);
});

test("complex intent always gets options", () => {
  const analysis = understandIntent(
    "migrate analytics pipeline to a new warehouse",
  );
  const result = resolveDecisionPoint(analysis);

  expect(result).not.toBeNull();
  expect(result!.options).toHaveLength(3);
});

test("research intent gets options", () => {
  const analysis = understandIntent(
    "compare bun and node startup time for the cli",
  );
  const result = resolveDecisionPoint(analysis);

  expect(result).not.toBeNull();
  expect(result!.options).toHaveLength(3);
});
