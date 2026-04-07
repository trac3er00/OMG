import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import {
  MIN_HANDOFF_RETENTION,
  MIN_CASCADING_RETENTION,
  DEFAULT_MAX_RETRIES,
  executeContextHandoff,
  executeCascadingHandoff,
  executeHandoffWithRetries,
  compactContextForRetry,
  getHandoffHealth,
  type HandoffHealthMetrics,
} from "./handoff-integration.js";
import {
  registerAgent,
  clearRegistry,
  type AgentCard,
} from "../orchestration/a2a.js";
import {
  createCompactState,
  serializeState,
} from "./workspace-reconstruction.js";

const TEST_DIR = "/tmp/omg-handoff-test";

const makeAgent = (id: string, maxTokens = 128_000): AgentCard => ({
  agent_id: id,
  name: `Agent ${id}`,
  capabilities: ["code-review"],
  risk_tier: "low",
  evidence_guarantee: true,
  max_context_tokens: maxTokens,
  version: "1.0.0",
});

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
  clearRegistry();
  const state = createCompactState("Test goal", {
    evidence_index: ["a.json"],
    decision_log: [
      {
        decision: "Use JWT",
        rationale: "Stateless",
        timestamp: new Date().toISOString(),
      },
    ],
  });
  serializeState(state, TEST_DIR);
});

afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("context/handoff-integration", () => {
  test("MIN_HANDOFF_RETENTION is 0.8", () => {
    expect(MIN_HANDOFF_RETENTION).toBe(0.8);
  });

  test("MIN_CASCADING_RETENTION is 0.6", () => {
    expect(MIN_CASCADING_RETENTION).toBe(0.6);
  });

  describe("executeContextHandoff", () => {
    test("successful handoff to registered agent", () => {
      const agent = makeAgent("agent-b", 128_000);
      registerAgent(agent);
      const state = createCompactState("Auth refactor", {
        evidence_index: ["tests.json"],
        decision_log: [
          {
            decision: "Use JWT",
            rationale: "Stateless",
            timestamp: new Date().toISOString(),
          },
        ],
      });

      const outcome = executeContextHandoff({
        from_agent_id: "agent-a",
        to_agent: agent,
        state,
        project_dir: TEST_DIR,
      });

      expect(outcome.result.success).toBe(true);
      expect(outcome.checkpoint_created).toBe(true);
      expect(outcome.pre_handoff_checkpoint_id).toBeDefined();
    });

    test("handoff creates pre-handoff checkpoint", () => {
      const agent = makeAgent("agent-b", 128_000);
      registerAgent(agent);
      const state = createCompactState("Goal");

      const outcome = executeContextHandoff({
        from_agent_id: "agent-a",
        to_agent: agent,
        state,
        project_dir: TEST_DIR,
      });

      expect(outcome.pre_handoff_checkpoint_id).not.toBeNull();
    });

    test("handoff fails for unregistered agent", () => {
      const agent = makeAgent("not-registered", 128_000);
      const state = createCompactState("Goal");

      const outcome = executeContextHandoff({
        from_agent_id: "agent-a",
        to_agent: agent,
        state,
        project_dir: TEST_DIR,
      });

      expect(outcome.result.success).toBe(false);
      expect(outcome.result.error).toBeDefined();
    });

    test("retention quality is measured", () => {
      const agent = makeAgent("agent-b", 128_000);
      registerAgent(agent);
      const state = createCompactState("Goal with decisions", {
        decision_log: [
          {
            decision: "D",
            rationale: "R",
            timestamp: new Date().toISOString(),
          },
        ],
      });

      const outcome = executeContextHandoff({
        from_agent_id: "agent-a",
        to_agent: agent,
        state,
        project_dir: TEST_DIR,
      });

      expect(outcome.retention_quality.retention_rate).toBeGreaterThan(0);
    });
  });

  describe("executeCascadingHandoff", () => {
    test("empty agent chain returns retention 1.0", () => {
      const state = createCompactState("Goal");
      const result = executeCascadingHandoff(state, [], "agent-a", TEST_DIR);
      expect(result.final_retention).toBe(1.0);
      expect(result.steps.length).toBe(0);
    });

    test("single hop with registered agent", () => {
      const agentB = makeAgent("agent-b", 128_000);
      registerAgent(agentB);
      const state = createCompactState("Goal");

      const result = executeCascadingHandoff(
        state,
        [agentB],
        "agent-a",
        TEST_DIR,
      );
      expect(result.steps.length).toBe(1);
      expect(result.final_retention).toBeGreaterThan(0);
    });

    test("cascading retention ≥ MIN_CASCADING_RETENTION for 2 hops", () => {
      const agentB = makeAgent("agent-b", 128_000);
      const agentC = makeAgent("agent-c", 128_000);
      registerAgent(agentB);
      registerAgent(agentC);

      const state = createCompactState("Goal with context", {
        evidence_index: ["a.json", "b.json"],
        decision_log: [
          {
            decision: "D1",
            rationale: "R1",
            timestamp: new Date().toISOString(),
          },
        ],
      });

      const result = executeCascadingHandoff(
        state,
        [agentB, agentC],
        "agent-a",
        TEST_DIR,
      );
      expect(result.steps.length).toBe(2);
      expect(result.final_retention).toBeGreaterThanOrEqual(
        MIN_CASCADING_RETENTION,
      );
    });

    test("stops cascade on failure", () => {
      const agentB = makeAgent("agent-b-unregistered", 128_000);
      const agentC = makeAgent("agent-c", 128_000);
      registerAgent(agentC);

      const state = createCompactState("Goal");
      const result = executeCascadingHandoff(
        state,
        [agentB, agentC],
        "agent-a",
        TEST_DIR,
      );
      expect(result.steps.length).toBeGreaterThan(0);
      expect(result.steps[0]?.outcome.result.success).toBe(false);
    });
  });

  describe("retry optimization", () => {
    test("DEFAULT_MAX_RETRIES is 3", () => {
      expect(DEFAULT_MAX_RETRIES).toBe(3);
    });

    test("compactContextForRetry increments context_version", () => {
      const state = createCompactState("Goal");
      const compacted = compactContextForRetry(state);
      expect(compacted.context_version).toBe(state.context_version + 1);
      expect(compacted.reconstructed_at).toBeDefined();
    });

    test("getHandoffHealth reports correct metrics on success", () => {
      const health: HandoffHealthMetrics = getHandoffHealth(
        2,
        3,
        [500, 300],
        true,
      );
      expect(health.success).toBe(true);
      expect(health.attemptCount).toBe(2);
      expect(health.maxRetries).toBe(3);
      expect(health.tokenWaste).toBe(500);
      expect(health.successRate).toBeCloseTo(0.5);
    });

    test("getHandoffHealth reports all tokens as waste on failure", () => {
      const health = getHandoffHealth(3, 3, [500, 400, 300], false);
      expect(health.success).toBe(false);
      expect(health.tokenWaste).toBe(1200);
      expect(health.successRate).toBe(0);
    });

    test("executeHandoffWithRetries succeeds on registered agent", () => {
      const agent = makeAgent("agent-retry-ok", 128_000);
      registerAgent(agent);
      const state = createCompactState("Retry goal");

      const { outcome, health } = executeHandoffWithRetries(
        {
          from_agent_id: "agent-a",
          to_agent: agent,
          state,
          project_dir: TEST_DIR,
        },
        3,
      );

      expect(outcome.result.success).toBe(true);
      expect(health.success).toBe(true);
      expect(health.attemptCount).toBe(1);
      expect(health.tokenWaste).toBe(0);
      expect(health.successRate).toBe(1.0);
    });

    test("executeHandoffWithRetries exhausts budget on unregistered agent", () => {
      const agent = makeAgent("never-registered", 128_000);
      const state = createCompactState("Doomed goal");

      const { outcome, health } = executeHandoffWithRetries(
        {
          from_agent_id: "agent-a",
          to_agent: agent,
          state,
          project_dir: TEST_DIR,
        },
        2,
      );

      expect(outcome.result.success).toBe(false);
      expect(health.success).toBe(false);
      expect(health.attemptCount).toBe(2);
      expect(health.maxRetries).toBe(2);
      expect(health.tokenWaste).toBeGreaterThan(0);
    });
  });
});
