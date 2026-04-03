import { describe, test, expect } from "bun:test";

const LATENCY_BUDGET_MS = 500;
const INDIVIDUAL_FRONTIER_BUDGET_MS = 100;

async function measureOperation<T>(
  fn: () => T | Promise<T>,
): Promise<{ result: T; elapsed_ms: number }> {
  const start = performance.now();
  const result = await fn();
  const elapsed_ms = performance.now() - start;
  return { result, elapsed_ms };
}

describe("hooks/performance", () => {
  describe("Context Durability hook performance", () => {
    test("strategy selection completes in ≤100ms", async () => {
      const { evaluateStrategies } =
        await import("../context/strategy-router.js");
      const state = {
        totalTokens: 75000,
        maxTokens: 100000,
        turnCount: 25,
        hasRecentDecisions: true,
        hasEvidenceRefs: true,
      };
      const { elapsed_ms } = await measureOperation(() =>
        evaluateStrategies(state),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });

    test("compression completes in ≤100ms", async () => {
      const { compress } = await import("../context/compression.js");
      const state = {
        totalTokens: 85000,
        maxTokens: 100000,
        turnCount: 30,
        hasRecentDecisions: true,
        hasEvidenceRefs: true,
      };
      const { elapsed_ms } = await measureOperation(() => compress(state));
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });
  });

  describe("Governance hook performance", () => {
    test("state machine transition completes in ≤100ms", async () => {
      const { GovernanceGraphRuntime } = await import("../governance/graph.js");
      const runtime = new GovernanceGraphRuntime("/tmp/perf-test");
      runtime.addNode("perf-test-node");
      const { elapsed_ms } = await measureOperation(() =>
        runtime.transition("perf-test-node", "implementing"),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });
  });

  describe("Society of Thought hook performance", () => {
    test("perspective activation check completes in ≤100ms", async () => {
      const { shouldActivateSoT } = await import("../debate/perspectives.js");
      const { elapsed_ms } = await measureOperation(() =>
        shouldActivateSoT({
          complexity_level: 4,
          domain: "security",
          is_high_stakes: true,
        }),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });

    test("voting on 3 perspectives completes in ≤100ms", async () => {
      const { conductVote } = await import("../debate/voting.js");
      const { createPerspectiveOutput } =
        await import("../debate/perspectives.js");
      const perspectives = [
        createPerspectiveOutput("proposer", "Test", { confidence: 0.9 }),
        createPerspectiveOutput("critic", "Review", { confidence: 0.7 }),
        createPerspectiveOutput("red-team", "Risk", { confidence: 0.5 }),
      ];
      const { elapsed_ms } = await measureOperation(() =>
        conductVote(perspectives),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });
  });

  describe("Reliability hook performance", () => {
    test("consistency metric completes in ≤100ms", async () => {
      const { measureSameInputConsistency } =
        await import("../reliability/metrics.js");
      const outputs = Array.from({ length: 10 }, () => "output-A");
      const { elapsed_ms } = await measureOperation(() =>
        measureSameInputConsistency(outputs),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });
  });

  describe("Metacognitive hook performance", () => {
    test("epistemic assessment completes in ≤100ms", async () => {
      const { assessEpistemicState } =
        await import("../metacognitive/epistemic-tracker.js");
      const { elapsed_ms } = await measureOperation(() =>
        assessEpistemicState({
          confidence: 0.8,
          source: "claim_judge",
          evidence_refs: ["a.json"],
        }),
      );
      expect(elapsed_ms).toBeLessThan(INDIVIDUAL_FRONTIER_BUDGET_MS);
    });
  });

  describe("Combined pipeline performance", () => {
    test("full frontier pipeline completes in ≤500ms for typical operation", async () => {
      const { runFrontierPipeline } =
        await import("../integration/frontier-pipeline.js");
      const { mkdirSync, rmSync } = await import("node:fs");
      const { join } = await import("node:path");
      const { createCompactState, serializeState } =
        await import("../context/workspace-reconstruction.js");
      const { clearRegistry } = await import("../orchestration/a2a.js");

      const testDir = "/tmp/perf-pipeline-test";
      rmSync(testDir, { recursive: true, force: true });
      mkdirSync(join(testDir, ".omg", "state"), { recursive: true });
      serializeState(createCompactState("Perf test"), testDir);
      clearRegistry();

      const { elapsed_ms } = await measureOperation(() =>
        runFrontierPipeline({
          sessionId: "perf-test",
          projectDir: testDir,
          contextState: {
            totalTokens: 50000,
            maxTokens: 100000,
            turnCount: 20,
            hasRecentDecisions: true,
            hasEvidenceRefs: true,
          },
          claim: "Implementation complete",
          claimConfidence: 0.85,
          evidenceRefs: ["proof.json"],
          taskComplexity: 2,
        }),
      );

      rmSync(testDir, { recursive: true, force: true });
      expect(elapsed_ms).toBeLessThan(LATENCY_BUDGET_MS);
    });
  });
});
