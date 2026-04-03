import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { ContextEngineeringSystem } from "./context-engineering.js";
import {
  createCompactState,
  serializeState,
} from "./workspace-reconstruction.js";
import {
  registerAgent,
  clearRegistry,
  type AgentCard,
} from "../orchestration/a2a.js";

const TEST_DIR = "/tmp/omg-ctx-eng-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
  const state = createCompactState("Test goal");
  serializeState(state, TEST_DIR);
  clearRegistry();
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

const baseState = {
  totalTokens: 75000,
  maxTokens: 100000,
  turnCount: 25,
  hasRecentDecisions: true,
  hasEvidenceRefs: true,
};

describe("context/context-engineering", () => {
  test("compress reduces token count", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const result = sys.compress({ ...baseState, totalTokens: 85000 });
    expect(result.compressed_tokens).toBeLessThan(85000);
  });

  test("evaluate returns null below threshold", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    expect(sys.evaluate({ ...baseState, totalTokens: 30000 })).toBeNull();
  });

  test("evaluate returns strategy above threshold", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const result = sys.evaluate({ ...baseState, totalTokens: 75000 });
    expect(result?.selected).toBeDefined();
  });

  test("reconstruct persists state", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const state = createCompactState("New goal");
    sys.reconstruct(state);
    const { deserializeState: ds } = require("./workspace-reconstruction.js");
    expect(ds(TEST_DIR)?.goal).toBe("New goal");
  });

  test("checkpoint creates checkpoint file", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const result = sys.checkpoint();
    expect(result.checkpoint_id).toBeDefined();
  });

  test("handoff fails for unregistered agent", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const agent: AgentCard = {
      agent_id: "unregistered",
      name: "Test",
      capabilities: ["code-review"],
      risk_tier: "low",
      evidence_guarantee: true,
      max_context_tokens: 128_000,
      version: "1.0.0",
    };
    const result = sys.handoff(createCompactState("Goal"), agent, "source");
    expect(result.success).toBe(false);
  });

  test("handoff succeeds for registered agent", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const agent: AgentCard = {
      agent_id: "reg-agent",
      name: "Test",
      capabilities: ["code-review"],
      risk_tier: "low",
      evidence_guarantee: true,
      max_context_tokens: 128_000,
      version: "1.0.0",
    };
    registerAgent(agent);
    const result = sys.handoff(createCompactState("Goal"), agent, "source");
    expect(result.success).toBe(true);
  });

  test("measure returns pressure metrics", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    const metrics = sys.measure({ ...baseState, totalTokens: 75000 });
    expect(metrics.pressure).toBeCloseTo(0.75, 5);
    expect(["advisory", "automatic", "emergency"]).toContain(
      metrics.pressure_level,
    );
    expect(metrics.checkpoint_count).toBe(0);
  });

  test("checkpoint_count tracks all checkpoints", () => {
    const sys = new ContextEngineeringSystem(TEST_DIR);
    sys.checkpoint();
    sys.checkpoint();
    sys.checkpoint();
    expect(sys.measure(baseState).checkpoint_count).toBe(3);
  });
});
