import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";
import {
  WORKSPACE_STATE_VERSION,
  CompactCanonicalStateSchema,
  createCompactState,
  serializeState,
  deserializeState,
  measureRetentionQuality,
  computeContextFreshnessScore,
  detectContextDecay,
  getWorkspaceDurabilityState,
  onContextDecayDetected,
  reconstructWorkspace,
} from "./workspace-reconstruction.js";

const TEST_DIR = "/tmp/omg-reconstruction-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
});

afterEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
});

describe("workspace-reconstruction", () => {
  describe("CompactCanonicalState schema", () => {
    test("valid state passes validation", () => {
      const state = {
        schema_version: "1.0.0",
        context_version: 1,
        goal: "Refactor auth module",
        evidence_index: ["tests.json"],
        open_hypotheses: ["JWT might be better"],
        decision_log: [
          {
            decision: "Use JWT",
            rationale: "Stateless",
            timestamp: new Date().toISOString(),
          },
        ],
        next_actions: ["Write tests"],
        reconstructed_at: new Date().toISOString(),
      };
      expect(CompactCanonicalStateSchema.safeParse(state).success).toBe(true);
    });

    test("wrong schema_version fails", () => {
      const state = {
        schema_version: "2.0.0",
        context_version: 0,
        goal: "Test",
        evidence_index: [],
        open_hypotheses: [],
        decision_log: [],
        next_actions: [],
        reconstructed_at: new Date().toISOString(),
      };
      expect(CompactCanonicalStateSchema.safeParse(state).success).toBe(false);
    });
  });

  describe("createCompactState", () => {
    test("creates state with goal and defaults", () => {
      const state = createCompactState("Build context system");
      expect(state.goal).toBe("Build context system");
      expect(state.schema_version).toBe(WORKSPACE_STATE_VERSION);
      expect(state.context_version).toBe(0);
      expect(state.evidence_index).toEqual([]);
      expect(state.decision_log).toEqual([]);
    });

    test("creates state with custom fields", () => {
      const state = createCompactState("Goal", {
        evidence_index: ["a.json", "b.json"],
        context_version: 5,
        next_actions: ["step 1"],
      });
      expect(state.evidence_index).toEqual(["a.json", "b.json"]);
      expect(state.context_version).toBe(5);
      expect(state.next_actions).toEqual(["step 1"]);
    });
  });

  describe("serialize/deserialize", () => {
    test("round-trip preserves all fields", () => {
      const original = createCompactState("Auth refactor", {
        evidence_index: ["test.json"],
        decision_log: [
          {
            decision: "Use JWT",
            rationale: "Stateless",
            timestamp: new Date().toISOString(),
          },
        ],
        next_actions: ["Write unit tests"],
      });

      serializeState(original, TEST_DIR);
      const loaded = deserializeState(TEST_DIR);

      expect(loaded).not.toBeNull();
      expect(loaded?.goal).toBe("Auth refactor");
      expect(loaded?.evidence_index).toEqual(["test.json"]);
      expect(loaded?.decision_log.length).toBe(1);
      expect(loaded?.decision_log[0]?.decision).toBe("Use JWT");
    });

    test("deserializeState returns null when no file exists", () => {
      const result = deserializeState("/tmp/nonexistent-dir-xyz");
      expect(result).toBeNull();
    });

    test("state file is persisted atomically (file exists after write)", () => {
      const state = createCompactState("Test goal");
      serializeState(state, TEST_DIR);
      const statePath = join(TEST_DIR, ".omg", "state", "workspace-state.json");
      expect(existsSync(statePath)).toBe(true);
    });
  });

  describe("measureRetentionQuality", () => {
    test("identical states have retention_rate 1.0", () => {
      const state = createCompactState("Goal", {
        evidence_index: ["a.json"],
        decision_log: [
          {
            decision: "D",
            rationale: "R",
            timestamp: new Date().toISOString(),
          },
        ],
      });
      const quality = measureRetentionQuality(state, { ...state });
      expect(quality.retention_rate).toBe(1.0);
    });

    test("completely different state has low retention_rate", () => {
      const original = createCompactState("Original goal", {
        evidence_index: ["a.json"],
        decision_log: [
          {
            decision: "Use JWT",
            rationale: "X",
            timestamp: new Date().toISOString(),
          },
        ],
      });
      const reconstructed = createCompactState("Different goal", {
        evidence_index: [],
        decision_log: [],
      });
      const quality = measureRetentionQuality(original, reconstructed);
      expect(quality.retention_rate).toBeLessThan(0.5);
    });

    test("preserved fields are populated", () => {
      const state = createCompactState("Same goal");
      const quality = measureRetentionQuality(state, { ...state });
      expect(quality.fields_preserved).toContain("goal");
    });

    test("lost fields tracked when goal differs", () => {
      const original = createCompactState("Original");
      const different = { ...original, goal: "Changed" };
      const quality = measureRetentionQuality(original, different);
      expect(quality.fields_lost).toContain("goal");
    });

    test("goal preservation contributes 0.4 weight to retention", () => {
      const original = createCompactState("Same goal");
      const reconstructed = createCompactState("Same goal");
      const quality = measureRetentionQuality(original, reconstructed);
      expect(quality.retention_rate).toBeGreaterThanOrEqual(0.4);
    });
  });

  describe("durability hardening", () => {
    test("freshness scoring scales with recent-reference density instead of always saturating", () => {
      const now = new Date("2026-04-07T12:00:00.000Z");
      const sparseScore = computeContextFreshnessScore({
        fileReferences: Array.from({ length: 6 }, (_, index) => ({
          path: `src/sparse-${index}.ts`,
          referencedAt: new Date(now.getTime() - 4 * 60_000).toISOString(),
        })),
        sessionStartedAt: new Date(now.getTime() - 20 * 60_000).toISOString(),
        now: now.toISOString(),
      });
      const saturatedScore = computeContextFreshnessScore({
        fileReferences: Array.from({ length: 12 }, (_, index) => ({
          path: `src/dense-${index}.ts`,
          referencedAt: new Date(now.getTime() - 2 * 60_000).toISOString(),
        })),
        sessionStartedAt: new Date(now.getTime() - 10 * 60_000).toISOString(),
        now: now.toISOString(),
      });

      expect(sparseScore).toBe(30);
      expect(saturatedScore).toBe(100);
      expect(sparseScore).toBeLessThan(saturatedScore);
    });

    test("freshness score computed correctly across context age", () => {
      const now = new Date("2026-04-07T12:00:00.000Z");
      const recentReferences = Array.from({ length: 12 }, (_, index) => ({
        path: `src/file-${index}.ts`,
        referencedAt: new Date(now.getTime() - 5 * 60_000).toISOString(),
      }));

      const freshScore = computeContextFreshnessScore({
        fileReferences: recentReferences,
        sessionStartedAt: new Date(now.getTime() - 10 * 60_000).toISOString(),
        now: now.toISOString(),
      });
      const staleScore = computeContextFreshnessScore({
        fileReferences: recentReferences,
        sessionStartedAt: new Date(now.getTime() - 40 * 60_000).toISOString(),
        now: now.toISOString(),
      });

      expect(freshScore).toBeGreaterThan(80);
      expect(staleScore).toBeLessThan(50);
    });

    test("decay detection emits event when efficiency falls below threshold", () => {
      const received: number[] = [];
      const unsubscribe = onContextDecayDetected((event) => {
        received.push(event.freshnessScore);
      });

      const result = detectContextDecay(
        {
          fileReferences: [
            {
              path: "src/old.ts",
              referencedAt: "2026-04-07T11:40:00.000Z",
            },
          ],
          sessionStartedAt: "2026-04-07T11:00:00.000Z",
          now: "2026-04-07T12:00:00.000Z",
        },
        0.3,
      );

      unsubscribe();

      expect(result.decayDetected).toBe(true);
      expect(received.length).toBeGreaterThan(0);
      expect(getWorkspaceDurabilityState().decayEventCount).toBeGreaterThan(0);
    });

    test("reconstructWorkspace persists durability metadata", async () => {
      const state = createCompactState("Durability goal", {
        evidence_index: ["a.json"],
        next_actions: ["reconstruct"],
      });

      const result = await reconstructWorkspace({
        projectDir: TEST_DIR,
        state,
        fileReferences: Array.from({ length: 10 }, (_, index) => ({
          path: `src/recent-${index}.ts`,
          referencedAt: "2026-04-07T11:55:00.000Z",
        })),
        sessionStartedAt: "2026-04-07T11:50:00.000Z",
        now: "2026-04-07T12:00:00.000Z",
      });
      const saved = deserializeState(TEST_DIR);

      expect(result.attempts).toBe(1);
      expect(saved?.contextFreshnessScore).toBeGreaterThan(80);
      expect(saved?.lastReconstructionAt).toBeDefined();
      expect(typeof saved?.decayEventCount).toBe("number");
    });
  });
});
