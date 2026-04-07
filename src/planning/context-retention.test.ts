import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readJsonFile } from "../state/atomic-io.js";
import {
  FilePlanningContextStore,
  PLANNING_CONTEXT_MEMORY_TIER,
  type PlanningContext,
} from "./context-retention.js";

let testDir = "";

function createTestDir(): string {
  return join(
    tmpdir(),
    `omg-planning-context-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
}

function createContext(
  overrides: Partial<PlanningContext> = {},
): PlanningContext {
  return {
    planId: "task-14-context-retention",
    topic: "Improve plan execution context durability",
    interviewDecisions: {
      persistence: "Use Ship-tier-backed file persistence for executor access",
      scope: "Persist interview decisions, research findings, and Metis review",
    },
    researchFindings: [
      "Checkpoint state already persists JSON under .omg/state",
      "Python CMMS exposes a dedicated Ship tier for durable memory",
    ],
    metisReview:
      "Executors need durable access to planning artifacts across restarts.",
    createdAt: "2026-04-07T00:00:00.000Z",
    version: "2.5.0",
    ...overrides,
  };
}

beforeEach(() => {
  testDir = createTestDir();
});

afterEach(() => {
  if (testDir.length > 0) {
    rmSync(testDir, { recursive: true, force: true });
  }
});

describe("planning context retention", () => {
  test("ship-persistence: planning context survives store reinitialization", async () => {
    const context = createContext();
    const writer = new FilePlanningContextStore(testDir);

    await writer.save(context);

    const storedPath = join(
      testDir,
      ".omg",
      "state",
      "planning-context",
      `${encodeURIComponent(context.planId)}.json`,
    );

    expect(existsSync(storedPath)).toBe(true);

    const saved = readJsonFile<{
      kind: string;
      tier: string;
      savedAt: string;
      context: PlanningContext;
    }>(storedPath);

    expect(saved?.kind).toBe("planning-context");
    expect(saved?.tier).toBe(PLANNING_CONTEXT_MEMORY_TIER);
    expect(saved?.context).toEqual(context);

    const reader = new FilePlanningContextStore(testDir);
    const loaded = await reader.load(context.planId);
    expect(loaded).toEqual(context);
  });

  test("load-nonexistent: returns null for unknown planId", async () => {
    const store = new FilePlanningContextStore(testDir);
    const loaded = await store.load("unknown-plan");
    expect(loaded).toBeNull();
  });

  test("exists-check: returns true after save and false before", async () => {
    const context = createContext({ planId: "exists-check-plan" });
    const store = new FilePlanningContextStore(testDir);

    expect(await store.exists(context.planId)).toBe(false);
    await store.save(context);
    expect(await store.exists(context.planId)).toBe(true);
  });
});
