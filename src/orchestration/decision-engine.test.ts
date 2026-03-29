import { describe, expect, test } from "bun:test";

import { recommendAgent, scoreComplexity } from "./decision-engine.js";

describe("scoreComplexity", () => {
  test("fix typo → trivial", () => {
    expect(scoreComplexity("fix typo in readme")).toBe("trivial");
  });

  test("fix spelling → trivial", () => {
    expect(scoreComplexity("fix spelling error")).toBe("trivial");
  });

  test("rename file → trivial", () => {
    expect(scoreComplexity("rename file to new name")).toBe("trivial");
  });

  test("simple change → simple", () => {
    expect(scoreComplexity("make a simple update")).toBe("simple");
  });

  test("add comment → simple", () => {
    expect(scoreComplexity("add comment to function")).toBe("simple");
  });

  test("quick fix → simple", () => {
    expect(scoreComplexity("quick fix for the header")).toBe("simple");
  });

  test("implement feature → moderate", () => {
    expect(scoreComplexity("implement user profile page")).toBe("moderate");
  });

  test("refactor module → moderate", () => {
    expect(scoreComplexity("refactor the auth module")).toBe("moderate");
  });

  test("fix bug → moderate", () => {
    expect(scoreComplexity("fix bug in payment processing")).toBe("moderate");
  });

  test("build auth system with OAuth → complex", () => {
    expect(scoreComplexity("build auth system with OAuth")).toBe("complex");
  });

  test("design system architecture → complex", () => {
    expect(scoreComplexity("design system for microservices")).toBe("complex");
  });

  test("security audit → complex", () => {
    expect(scoreComplexity("run security audit on api")).toBe("complex");
  });

  test("performance optimization → complex", () => {
    expect(scoreComplexity("performance optimization of queries")).toBe("complex");
  });

  test("rewrite entire codebase → extreme", () => {
    expect(scoreComplexity("rewrite entire frontend")).toBe("extreme");
  });

  test("machine learning pipeline → extreme", () => {
    expect(scoreComplexity("build machine learning model")).toBe("extreme");
  });

  test("novel algorithm → extreme", () => {
    expect(scoreComplexity("design novel algorithm for sorting")).toBe("extreme");
  });

  test("unknown task → moderate (default)", () => {
    expect(scoreComplexity("do something unrecognizable")).toBe("moderate");
  });
});

describe("recommendAgent", () => {
  test("returns AgentRecommendation shape", () => {
    const rec = recommendAgent("fix typo in readme");
    expect(rec).toHaveProperty("agentName");
    expect(rec).toHaveProperty("category");
    expect(rec).toHaveProperty("provider");
    expect(rec).toHaveProperty("confidence");
    expect(rec).toHaveProperty("fallback");
    expect(rec).toHaveProperty("reasoning");
    expect(rec).toHaveProperty("complexity");
  });

  test("trivial task has higher confidence boost", () => {
    const rec = recommendAgent("fix typo");
    expect(rec.complexity).toBe("trivial");
    expect(rec.confidence).toBeGreaterThanOrEqual(0.5);
  });

  test("security keyword → security-auditor agent", () => {
    const rec = recommendAgent("run security audit on the codebase");
    expect(rec.agentName).toBe("security-auditor");
    expect(rec.category).toBe("ultrabrain");
  });

  test("code keyword → codex agent", () => {
    const rec = recommendAgent("code a new feature");
    expect(rec.agentName).toBe("codex");
    expect(rec.category).toBe("deep");
  });

  test("research keyword → gemini agent", () => {
    const rec = recommendAgent("research the latest trends");
    expect(rec.agentName).toBe("gemini");
    expect(rec.category).toBe("ultrabrain");
  });

  test("ui keyword → frontend-designer", () => {
    const rec = recommendAgent("build a new ui component");
    expect(rec.agentName).toBe("frontend-designer");
    expect(rec.category).toBe("visual-engineering");
  });

  test("database keyword → database-engineer", () => {
    const rec = recommendAgent("create database migration");
    expect(rec.agentName).toBe("database-engineer");
  });

  test("deploy keyword → infra-engineer", () => {
    const rec = recommendAgent("deploy to kubernetes cluster");
    expect(rec.agentName).toBe("infra-engineer");
  });

  test("unknown domain → task agent with unspecified-high category", () => {
    const rec = recommendAgent("do something random");
    expect(rec.agentName).toBe("task");
    expect(rec.category).toBe("unspecified-high");
  });

  test("domain match increases confidence", () => {
    const withDomain = recommendAgent("run security audit");
    const withoutDomain = recommendAgent("do something random here");
    expect(withDomain.confidence).toBeGreaterThan(withoutDomain.confidence);
  });

  test("fallback excludes primary provider", () => {
    const rec = recommendAgent("fix typo");
    expect(rec.fallback).not.toContain(rec.provider);
  });

  test("reasoning includes complexity and domain info", () => {
    const rec = recommendAgent("build auth system with OAuth");
    expect(rec.reasoning).toContain("Complexity=complex");
    expect(rec.reasoning).toContain("Provider=");
  });
});
