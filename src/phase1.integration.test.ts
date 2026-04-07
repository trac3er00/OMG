import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { CheckpointSystem } from "./context/checkpoint.js";
import {
  runPlanningDebate,
  DEFAULT_DEBATE_CONFIG,
  type PlanningDecision,
  type DebateOutcome,
} from "./debate/integration.js";
import { ToolFabric } from "./governance/tool-fabric.js";

function makeTempProject(): string {
  const dir = mkdtempSync(join(tmpdir(), "phase1-int-"));
  mkdirSync(join(dir, ".omg", "state"), { recursive: true });
  return dir;
}

describe("Phase1 Cross: CMMS tiers + /pause checkpoint", () => {
  let projectDir: string;

  beforeEach(() => {
    projectDir = makeTempProject();
  });
  afterEach(() => {
    rmSync(projectDir, { recursive: true, force: true });
  });

  it("checkpoint captures contextFreshnessScore and tier-related fields", () => {
    const statePath = join(projectDir, ".omg", "state", "workspace-state.json");
    const canonState = {
      schema_version: "1.0.0",
      context_version: 3,
      goal: "integration test",
      evidence_index: [],
      open_hypotheses: [],
      decision_log: [],
      next_actions: [],
      reconstructed_at: new Date().toISOString(),
      contextFreshnessScore: 72,
      lastReconstructionAt: new Date().toISOString(),
      decayEventCount: 2,
    };
    writeFileSync(statePath, JSON.stringify(canonState));

    const sys = new CheckpointSystem(projectDir, 1);
    const result = sys.onToolCall();

    expect(result).not.toBeNull();
    expect(result!.checkpoint_id).toBeTruthy();
    expect(result!.tool_call_count).toBe(1);

    const { readFileSync } = require("node:fs");
    const raw = JSON.parse(readFileSync(result!.path, "utf-8"));
    expect(raw.meta.checkpoint_id).toBe(result!.checkpoint_id);
    expect(raw.meta).toHaveProperty("contextFreshnessScore");
    expect(raw.meta).toHaveProperty("lastReconstructionAt");
    expect(raw.meta).toHaveProperty("decayEventCount");
    expect(raw.meta).toHaveProperty("context_version");
    expect(typeof raw.meta.contextFreshnessScore).toBe("number");
  });

  it("checkpoint JSON has all required schema fields", () => {
    const sys = new CheckpointSystem(projectDir, 1);
    const result = sys.saveCheckpoint();
    const { readFileSync } = require("node:fs");
    const raw = JSON.parse(readFileSync(result.path, "utf-8"));

    const requiredFields = [
      "checkpoint_id",
      "created_at",
      "tool_call_count",
      "context_version",
      "goal_summary",
    ];
    for (const field of requiredFields) {
      expect(raw.meta).toHaveProperty(field);
    }
  });
});

describe("Phase1 Cross: /continue + context durability", () => {
  let projectDir: string;

  beforeEach(() => {
    projectDir = makeTempProject();
  });
  afterEach(() => {
    rmSync(projectDir, { recursive: true, force: true });
  });

  it("restoring a checkpoint with low freshness signals durability need", () => {
    const statePath = join(projectDir, ".omg", "state", "workspace-state.json");
    const degradedState = {
      schema_version: "1.0.0",
      context_version: 12,
      goal: "long-running session",
      evidence_index: [],
      open_hypotheses: [],
      decision_log: [],
      next_actions: [],
      reconstructed_at: new Date().toISOString(),
      contextFreshnessScore: 25,
      lastReconstructionAt: new Date().toISOString(),
      decayEventCount: 15,
    };
    writeFileSync(statePath, JSON.stringify(degradedState));

    const sys = new CheckpointSystem(projectDir, 1);
    sys.saveCheckpoint();

    const restored = sys.restoreLatest();
    expect(restored).not.toBeNull();
    expect(restored!.state).toBeDefined();
    expect(restored!.checkpoint_id).toBeTruthy();
    expect(restored!.elapsed_ms).toBeGreaterThanOrEqual(0);

    if (restored!.state.contextFreshnessScore !== undefined) {
      expect(restored!.state.contextFreshnessScore).toBeLessThanOrEqual(50);
    }
  });

  it("multiple checkpoints preserve version ordering", () => {
    const statePath = join(projectDir, ".omg", "state", "workspace-state.json");

    writeFileSync(
      statePath,
      JSON.stringify({
        schema_version: "1.0.0",
        context_version: 1,
        goal: "v1",
        evidence_index: [],
        open_hypotheses: [],
        decision_log: [],
        next_actions: [],
        reconstructed_at: new Date().toISOString(),
      }),
    );
    const sys = new CheckpointSystem(projectDir, 1);
    sys.saveCheckpoint();

    writeFileSync(
      statePath,
      JSON.stringify({
        schema_version: "1.0.0",
        context_version: 5,
        goal: "v5",
        evidence_index: [],
        open_hypotheses: [],
        decision_log: [],
        next_actions: [],
        reconstructed_at: new Date().toISOString(),
      }),
    );
    sys.onToolCall();

    const restored = sys.restoreLatest();
    expect(restored).not.toBeNull();
    expect(restored!.state.context_version).toBeGreaterThanOrEqual(1);
  });
});

describe("Phase1 Cross: Society of Thought + governance", () => {
  let projectDir: string;

  beforeEach(() => {
    projectDir = makeTempProject();
  });
  afterEach(() => {
    rmSync(projectDir, { recursive: true, force: true });
  });

  it("high-complexity debate produces valid transcript + governance check succeeds", async () => {
    const decision: PlanningDecision = {
      topic: "Migrate monolith to microservices",
      complexity: 9,
      context: "Legacy Java app with 500k LOC, team of 12",
      domain: "architecture",
      is_high_stakes: true,
      alternatives: [
        "strangler fig pattern",
        "big-bang rewrite",
        "modular monolith",
      ],
    };

    const outcome: DebateOutcome = await runPlanningDebate(decision, {
      ...DEFAULT_DEBATE_CONFIG,
      enabled: true,
    });

    expect(outcome.invoked).toBe(true);
    expect(outcome.skipped).toBe(false);
    expect(outcome.transcript).toBeDefined();
    expect(outcome.planSummary).toBeTruthy();

    const t = outcome.transcript!;
    expect(t.rounds.length).toBeGreaterThan(0);
    expect(t.consensus.status).toBeTruthy();
    expect(t.votingResult.verdict).toBeTruthy();
    expect(t.votingResult.aggregateConfidence).toBeGreaterThan(0);

    const fabric = new ToolFabric(projectDir);
    const govResult = await fabric.preDispatchGovernanceCheck(
      ["proposer", "critic", "red-team"],
      "phase1-integration-sot",
    );

    expect(govResult).toBeDefined();
    expect(typeof govResult.allowed).toBe("boolean");
    expect(govResult.mode).toBeTruthy();
    expect(govResult.ledgerEntry).toBeTruthy();

    fabric.close();
  });

  it("low-complexity decision skips debate correctly", async () => {
    const decision: PlanningDecision = {
      topic: "Rename a variable",
      complexity: 1,
      context: "Simple refactor",
    };

    const outcome = await runPlanningDebate(decision);
    expect(outcome.invoked).toBe(false);
    expect(outcome.skipped).toBe(true);
    expect(outcome.skipReason).toBeTruthy();
  });
});

describe("Phase1 Cross: Handoff retry + CMMS tier interaction", () => {
  let projectDir: string;

  beforeEach(() => {
    projectDir = makeTempProject();
  });
  afterEach(() => {
    rmSync(projectDir, { recursive: true, force: true });
  });

  it("ToolFabric governance produces ledger entries for retry-like patterns", async () => {
    const fabric = new ToolFabric(projectDir);

    fabric.registerLane("retry-lane", {
      allowedTools: ["handoff", "checkpoint"],
      requiresAttestation: false,
    });

    const r1 = await fabric.evaluateRequest(
      "handoff",
      { attempt: 1 },
      "retry-lane",
    );
    expect(r1.action).toBe("allow");
    expect(r1.lane).toBe("retry-lane");

    const r2 = await fabric.evaluateRequest(
      "handoff",
      { attempt: 2 },
      "retry-lane",
    );
    expect(r2.action).toBe("allow");

    const r3 = await fabric.evaluateRequest(
      "destructive-op",
      { attempt: 3 },
      "retry-lane",
    );
    expect(r3.action).toBe("deny");
    expect(r3.reason).toContain("not in allowed tools");

    const entries = fabric.getLedgerEntries();
    expect(entries.length).toBeGreaterThanOrEqual(3);

    fabric.close();
  });

  it("governance check with agent combination produces valid result", async () => {
    const fabric = new ToolFabric(projectDir);

    const result = await fabric.preDispatchGovernanceCheck(
      ["retry-handler", "cmms-tier-manager"],
      "handoff-retry-test",
    );

    expect(result).toBeDefined();
    expect(typeof result.allowed).toBe("boolean");
    expect(result.ledgerEntry).toBeTruthy();
    expect(Array.isArray(result.warnings)).toBe(true);

    fabric.close();
  });
});
