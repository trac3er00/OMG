import { describe, expect, test } from "bun:test";
import { OrchestrationSession, INITIAL_DURABILITY_METRICS } from "./session.js";
import type { SessionEvent } from "./session-events.js";

function createTimeController(initialTime: string) {
  let currentTime = new Date(initialTime);
  return {
    now: () => currentTime,
    advance(minutes: number) {
      currentTime = new Date(currentTime.getTime() + minutes * 60_000);
    },
  };
}

describe("Session Lifecycle — Context Durability", () => {
  test("emits context-decay-detected when freshness drops below threshold", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");
    const events: SessionEvent[] = [];

    const session = OrchestrationSession.create({
      idGenerator: () => "decay-test-1",
      now: time.now,
      freshnessThreshold: 40,
      projectDir: `/tmp/omg-decay-test-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });

    session.on("event", (e: SessionEvent) => events.push(e));

    // Record file references at the current time
    session.recordFileReference("src/foo.ts");
    session.recordFileReference("src/bar.ts");

    // Advance time well past the 10-minute freshness window
    time.advance(30);

    // Check freshness — refs are now stale
    const score = await session.checkFreshness();
    expect(score).toBeLessThan(40);

    // Verify context-decay-detected event was emitted
    const decayEvents = events.filter(
      (e) => e.type === "context-decay-detected",
    );
    expect(decayEvents.length).toBe(1);
    expect(decayEvents[0]!.payload.freshnessScore).toBeLessThan(40);
    expect(decayEvents[0]!.payload.threshold).toBe(40);

    // Verify durability metrics updated
    const metrics = session.getDurabilityMetrics();
    expect(metrics.decayEventCount).toBe(1);
  });

  test("freshness recovers after adding recent file references", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");

    const session = OrchestrationSession.create({
      idGenerator: () => "recovery-test-1",
      now: time.now,
      freshnessThreshold: 40,
      projectDir: `/tmp/omg-recovery-test-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });

    // Record a file reference
    session.recordFileReference("src/old.ts");

    // Advance time past the freshness window
    time.advance(15);

    // First check — should detect decay (0 recent refs / 15 min age)
    const lowScore = await session.checkFreshness();
    expect(lowScore).toBeLessThan(40);

    // Add fresh file references at the current time
    // Need enough for efficiencyRatio >= 0.4 (threshold/100)
    // With age=15min, need >= 15*0.4 = 6 recent refs for ratio >= 0.4
    for (let i = 0; i < 15; i++) {
      session.recordFileReference(`src/fresh-${i}.ts`);
    }

    // Second check — should show recovery (15 recent refs / 15 min = 1.0 ratio)
    const highScore = await session.checkFreshness();
    expect(highScore).toBeGreaterThanOrEqual(40);
  });

  test("checkFreshness tracks scores for periodic monitoring", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");

    const session = OrchestrationSession.create({
      idGenerator: () => "periodic-test-1",
      now: time.now,
      freshnessCheckIntervalMinutes: 5,
    });

    // Add fresh references
    for (let i = 0; i < 5; i++) {
      session.recordFileReference(`src/file-${i}.ts`);
    }

    // First check — refs are recent, score should be positive
    const score1 = await session.checkFreshness();
    expect(score1).toBeGreaterThanOrEqual(0);

    // Advance time slightly, add more refs
    time.advance(2);
    for (let i = 5; i < 10; i++) {
      session.recordFileReference(`src/file-${i}.ts`);
    }

    const score2 = await session.checkFreshness();
    expect(score2).toBeGreaterThanOrEqual(0);

    // Metrics should reflect average of both scores
    const metrics = session.getDurabilityMetrics();
    expect(typeof metrics.averageFreshnessScore).toBe("number");
    expect(metrics.averageFreshnessScore).toBeGreaterThanOrEqual(0);
    expect(metrics.averageFreshnessScore).toBeLessThanOrEqual(100);
  });

  test("snapshot includes durability metrics after decay event", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");

    const session = OrchestrationSession.create({
      idGenerator: () => "snapshot-test-1",
      now: time.now,
      freshnessThreshold: 40,
      projectDir: `/tmp/omg-snapshot-test-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });

    // Trigger decay
    session.recordFileReference("src/stale.ts");
    time.advance(30);
    await session.checkFreshness();

    // Verify snapshot includes durability metrics
    const snap = session.snapshot();
    expect(snap.durabilityMetrics).toBeDefined();
    expect(snap.durabilityMetrics.decayEventCount).toBe(1);
    expect(snap.durabilityMetrics.averageFreshnessScore).toBeDefined();
    expect(typeof snap.durabilityMetrics.totalReconstructions).toBe("number");
  });

  test("reconstruction is attempted when decay is detected", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");
    const events: SessionEvent[] = [];

    const session = OrchestrationSession.create({
      idGenerator: () => "recon-test-1",
      now: time.now,
      freshnessThreshold: 40,
      projectDir: `/tmp/omg-recon-test-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });

    session.on("event", (e: SessionEvent) => events.push(e));

    // Trigger decay
    session.recordFileReference("src/old.ts");
    time.advance(30);
    await session.checkFreshness();

    // Verify reconstruction was attempted (succeeded or failed event emitted)
    const reconEvents = events.filter(
      (e) =>
        e.type === "workspace_reconstructed" ||
        e.type === "reconstruction_failed",
    );
    expect(reconEvents.length).toBe(1);
  });

  test("getContextFreshnessScore returns last computed score", async () => {
    const time = createTimeController("2026-01-15T10:00:00Z");

    const session = OrchestrationSession.create({
      idGenerator: () => "score-test-1",
      now: time.now,
    });

    // Before any check, falls back to global state
    const initial = session.getContextFreshnessScore();
    expect(typeof initial).toBe("number");

    // After check, returns the computed score
    session.recordFileReference("src/test.ts");
    const score = await session.checkFreshness();
    expect(session.getContextFreshnessScore()).toBe(score);
  });

  test("default durability metrics for new session", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "default-metrics-1",
      now: () => new Date("2026-01-15T10:00:00Z"),
    });

    const metrics = session.getDurabilityMetrics();
    expect(metrics.totalReconstructions).toBe(0);
    expect(metrics.averageFreshnessScore).toBe(100);
    expect(metrics.decayEventCount).toBe(0);
    expect(metrics.lastReconstructionAt).toBeUndefined();
  });

  test("INITIAL_DURABILITY_METRICS constant matches defaults", () => {
    expect(INITIAL_DURABILITY_METRICS.totalReconstructions).toBe(0);
    expect(INITIAL_DURABILITY_METRICS.averageFreshnessScore).toBe(100);
    expect(INITIAL_DURABILITY_METRICS.decayEventCount).toBe(0);
  });
});
