import { describe, test, expect, beforeEach } from "bun:test";
import {
  A2A_VERSION,
  MAX_PREDEFINED_AGENTS,
  AgentCardSchema,
  registerAgent,
  getAgent,
  listAgents,
  clearRegistry,
  findAgentsByCapability,
  buildHandoffContext,
  executeHandoff,
  type AgentCard,
} from "./a2a.js";
import { createCompactState } from "../context/workspace-reconstruction.js";

beforeEach(() => clearRegistry());

const testCard = (id: string, maxTokens = 128_000): AgentCard => ({
  agent_id: id,
  name: `Test Agent ${id}`,
  capabilities: ["code-review", "testing"],
  risk_tier: "low",
  evidence_guarantee: true,
  max_context_tokens: maxTokens,
  version: A2A_VERSION,
});

describe("orchestration/a2a", () => {
  test("A2A_VERSION is defined", () => {
    expect(A2A_VERSION).toBe("1.0.0");
  });

  test("MAX_PREDEFINED_AGENTS is 10", () => {
    expect(MAX_PREDEFINED_AGENTS).toBe(10);
  });

  describe("AgentCard schema", () => {
    test("valid agent card passes", () => {
      expect(AgentCardSchema.safeParse(testCard("agent-1")).success).toBe(true);
    });

    test("invalid risk_tier fails", () => {
      const card = { ...testCard("agent-1"), risk_tier: "critical" };
      expect(AgentCardSchema.safeParse(card).success).toBe(false);
    });

    test("empty agent_id fails", () => {
      const card = { ...testCard("agent-1"), agent_id: "" };
      expect(AgentCardSchema.safeParse(card).success).toBe(false);
    });
  });

  describe("agent registry", () => {
    test("registerAgent adds agent to registry", () => {
      registerAgent(testCard("agent-1"));
      expect(getAgent("agent-1")).not.toBeNull();
    });

    test("getAgent returns null for unknown agent", () => {
      expect(getAgent("nonexistent")).toBeNull();
    });

    test("listAgents returns all registered agents", () => {
      registerAgent(testCard("a"));
      registerAgent(testCard("b"));
      expect(listAgents().length).toBe(2);
    });

    test("registry enforces MAX_PREDEFINED_AGENTS limit", () => {
      for (let i = 0; i < MAX_PREDEFINED_AGENTS; i++) {
        registerAgent(testCard(`agent-${i}`));
      }
      expect(() => registerAgent(testCard("one-too-many"))).toThrow(
        "Max agents",
      );
    });

    test("findAgentsByCapability returns matching agents", () => {
      registerAgent({ ...testCard("a"), capabilities: ["code-review"] });
      registerAgent({ ...testCard("b"), capabilities: ["security-audit"] });
      const results = findAgentsByCapability("code-review");
      expect(results.length).toBe(1);
      expect(results[0]?.agent_id).toBe("a");
    });
  });

  describe("buildHandoffContext", () => {
    test("builds context for small state (no compression)", () => {
      const state = createCompactState("Small goal", {
        evidence_index: ["a.json"],
      });
      const agent = testCard("big-agent", 128_000);
      const ctx = buildHandoffContext(state, agent);
      expect(ctx.compressed).toBe(false);
      expect(ctx.context_tokens).toBeGreaterThan(0);
    });

    test("compresses when state exceeds target window", () => {
      const state = createCompactState("Big goal");
      const tinyAgent = testCard("tiny-agent", 10);
      const ctx = buildHandoffContext(state, tinyAgent);
      expect(ctx.compressed).toBe(true);
    });
  });

  describe("executeHandoff", () => {
    test("successful handoff within token budget", () => {
      registerAgent(testCard("target", 128_000));
      const state = createCompactState("Goal", { evidence_index: ["a.json"] });
      const ctx = buildHandoffContext(state, testCard("target", 128_000));
      const result = executeHandoff("source-agent", "target", ctx);
      expect(result.success).toBe(true);
      expect(result.tokens_transferred).toBeGreaterThan(0);
    });

    test("fails for unknown target agent", () => {
      const state = createCompactState("Goal");
      const ctx = buildHandoffContext(state, testCard("nonexistent", 128_000));
      const result = executeHandoff("source", "nonexistent", ctx);
      expect(result.success).toBe(false);
      expect(result.error).toContain("Unknown agent");
    });

    test("uncompressed handoff has retention_rate 1.0", () => {
      registerAgent(testCard("target", 128_000));
      const state = createCompactState("Goal");
      const ctx = { state, context_tokens: 1000, compressed: false };
      const result = executeHandoff("source", "target", ctx);
      expect(result.retention_rate).toBe(1.0);
    });

    test("compressed handoff has lower retention_rate", () => {
      registerAgent(testCard("target", 128_000));
      const state = createCompactState("Goal");
      const ctx = { state, context_tokens: 1000, compressed: true };
      const result = executeHandoff("source", "target", ctx);
      expect(result.retention_rate).toBeLessThan(1.0);
    });
  });
});
