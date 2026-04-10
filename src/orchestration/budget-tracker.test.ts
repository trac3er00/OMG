import { describe, expect, test } from "bun:test";
import { BudgetTracker, DEFAULT_BUDGET } from "./budget-tracker.js";

describe("BudgetTracker", () => {
  test("DEFAULT_BUDGET exposes expected orchestration defaults", () => {
    expect(DEFAULT_BUDGET).toEqual({
      tokens: 500_000,
      wall_time_ms: 600_000,
      memory_mb: 2048,
    });
  });

  test("recordWallTime updates pressure and snapshot data", () => {
    const tracker = new BudgetTracker("session-1", {
      tokens: 1_000,
      wall_time_ms: 1_000,
      memory_mb: 256,
    });

    tracker.recordWallTime(250);

    expect(tracker.check().exceeded).toBe(false);
    expect(tracker.pressureSnapshot().wall_time_ms).toBe(0.25);
    expect(tracker.toSnapshot().wallTimeSecondsUsed).toBe(250);
  });
});
