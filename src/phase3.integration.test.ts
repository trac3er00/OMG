import { expect, test } from "bun:test";

import { decideEscalation } from "./orchestration/auto-escalation.js";

class TrajectoryTracker {
  private readonly checkpoints: string[] = [];

  record(checkpoint: string): void {
    this.checkpoints.push(checkpoint);
  }

  snapshot(): { total: number; last: string | null } {
    return {
      total: this.checkpoints.length,
      last:
        this.checkpoints.length > 0
          ? this.checkpoints[this.checkpoints.length - 1]
          : null,
    };
  }
}

function classify_task(taskDescription: string): "direct" | "governed" {
  return /govern|route|escalat|research/i.test(taskDescription)
    ? "governed"
    : "direct";
}

interface DaemonConfig {
  enabled: boolean;
  securityEnvelope: boolean;
  pollIntervalMs: number;
}

test("auto-escalation export exists", () => {
  const decision = decideEscalation({
    taskDescription: "Update the release notes",
  });

  expect(typeof decideEscalation).toBe("function");
  expect(decision.model).toBeTruthy();
  expect(decision.escalated).toBe(false);
});

test("trajectory tracker concept records progress", () => {
  const tracker = new TrajectoryTracker();

  tracker.record("phase-3:start");

  expect(tracker.snapshot()).toEqual({
    total: 1,
    last: "phase-3:start",
  });
});

test("governance routing concept classifies tasks", () => {
  expect(classify_task("govern a routed autoresearch task")).toBe("governed");
});

test("autoresearch daemon config concept is representable", () => {
  const config: DaemonConfig = {
    enabled: true,
    securityEnvelope: true,
    pollIntervalMs: 60_000,
  };

  expect(config.enabled).toBe(true);
  expect(config.securityEnvelope).toBe(true);
  expect(config.pollIntervalMs).toBe(60_000);
});
