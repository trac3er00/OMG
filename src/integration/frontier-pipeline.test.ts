import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import {
  runFrontierPipeline,
  FRONTIER_PIPELINE_VERSION,
  FrontierPipelineResultSchema,
} from "./frontier-pipeline.js";
import {
  createCompactState,
  serializeState,
} from "../context/workspace-reconstruction.js";
import { clearRegistry } from "../orchestration/a2a.js";

const TEST_DIR = "/tmp/omg-frontier-test";

const baseOpts = {
  sessionId: "test-session",
  projectDir: TEST_DIR,
  contextState: {
    totalTokens: 50000,
    maxTokens: 100000,
    turnCount: 20,
    hasRecentDecisions: true,
    hasEvidenceRefs: true,
  },
  claim: "Implementation is complete",
  claimConfidence: 0.85,
  evidenceRefs: ["tests.json", "coverage.json"],
};

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
  const state = createCompactState("Test session goal");
  serializeState(state, TEST_DIR);
  clearRegistry();
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("integration/frontier-pipeline", () => {
  test("FRONTIER_PIPELINE_VERSION is 1.0.0", () => {
    expect(FRONTIER_PIPELINE_VERSION).toBe("1.0.0");
  });

  test("runs successfully with basic options", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.session_id).toBe("test-session");
    expect(result.schema_version).toBe(FRONTIER_PIPELINE_VERSION);
  });

  test("result validates against schema", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(FrontierPipelineResultSchema.safeParse(result).success).toBe(true);
  });

  test("context durability frontier always active", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.frontiers_active).toContain("context-durability");
  });

  test("governance frontier always active", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.frontiers_active).toContain("governance");
  });

  test("reliability frontier always active", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.frontiers_active).toContain("reliability");
  });

  test("metacognitive frontier always active", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.frontiers_active).toContain("metacognitive");
  });

  test("society-of-thought activates for complex/high-stakes tasks", () => {
    const result = runFrontierPipeline({
      ...baseOpts,
      claimConfidence: 0.3,
      taskComplexity: 4,
      domain: "security",
    });
    expect(result.debate_activated).toBe(true);
    expect(result.frontiers_active).toContain("society-of-thought");
  });

  test("governance records transitions", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.governance_transitions.length).toBeGreaterThan(0);
  });

  test("metacognitive confidence is 0-1", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.metacognitive_confidence).toBeGreaterThanOrEqual(0);
    expect(result.metacognitive_confidence).toBeLessThanOrEqual(1);
  });

  test("frontier independence: each frontier reports independently", () => {
    const result = runFrontierPipeline(baseOpts);
    expect(result.context_pressure).toBeGreaterThanOrEqual(0);
    expect(result.reliability_score).toBeGreaterThanOrEqual(0);
    expect(typeof result.collusion_detected).toBe("boolean");
  });
});
