import { describe, expect, test } from "bun:test";

import {
  scoreToHudColor,
  scoreToHudBand,
  computeReliabilityHudData,
} from "./hud-integration";
import { aggregateSnapshot, type MetricResult } from "./metrics";

function fakeMetric(overrides: Partial<MetricResult> = {}): MetricResult {
  return {
    metric_id: overrides.metric_id ?? "same-input-consistency",
    dimension: overrides.dimension ?? "consistency",
    name: overrides.name ?? "Same-Input Consistency",
    score: overrides.score ?? 0.85,
    threshold: overrides.threshold ?? 0.8,
    status: overrides.status ?? "pass",
    sample_count: overrides.sample_count ?? 10,
  };
}

function fakeSnapshot(overallScore: number) {
  return aggregateSnapshot("agent-test", "unit", [
    fakeMetric({
      score: overallScore,
      status: overallScore >= 0.8 ? "pass" : "fail",
    }),
  ]);
}

describe("scoreToHudColor", () => {
  test("color-mapping", () => {
    expect(scoreToHudColor(0)).toBe("red");
    expect(scoreToHudColor(20)).toBe("red");
    expect(scoreToHudColor(25)).toBe("red");
    expect(scoreToHudColor(26)).toBe("orange");
    expect(scoreToHudColor(40)).toBe("orange");
    expect(scoreToHudColor(50)).toBe("orange");
    expect(scoreToHudColor(51)).toBe("yellow");
    expect(scoreToHudColor(60)).toBe("yellow");
    expect(scoreToHudColor(75)).toBe("yellow");
    expect(scoreToHudColor(76)).toBe("green");
    expect(scoreToHudColor(90)).toBe("green");
    expect(scoreToHudColor(100)).toBe("green");
  });
});

describe("scoreToHudBand", () => {
  test("band-mapping", () => {
    expect(scoreToHudBand(0)).toBe("critical");
    expect(scoreToHudBand(25)).toBe("critical");
    expect(scoreToHudBand(26)).toBe("low");
    expect(scoreToHudBand(50)).toBe("low");
    expect(scoreToHudBand(51)).toBe("medium");
    expect(scoreToHudBand(75)).toBe("medium");
    expect(scoreToHudBand(76)).toBe("high");
    expect(scoreToHudBand(100)).toBe("high");
  });
});

describe("computeReliabilityHudData", () => {
  test("panel", () => {
    const snapshots = [
      fakeSnapshot(0.6),
      fakeSnapshot(0.7),
      fakeSnapshot(0.85),
    ];

    const data = computeReliabilityHudData(snapshots);

    expect(data.reliability_score).toBeGreaterThanOrEqual(0);
    expect(data.reliability_score).toBeLessThanOrEqual(100);
    expect(data.reliability_score).toBe(85);
    expect(["critical", "low", "medium", "high"]).toContain(
      data.reliability_band,
    );
    expect(data.reliability_band).toBe("high");
    expect(data.hud_color).toBe("green");
    expect(data.trend).toBeArray();
    expect(data.trend.length).toBeLessThanOrEqual(5);
    expect(data.trend.length).toBe(3);
    expect(data.drift_alerts).toBeArray();
  });

  test("empty snapshots yield zero score and critical band", () => {
    const data = computeReliabilityHudData([]);

    expect(data.reliability_score).toBe(0);
    expect(data.reliability_band).toBe("critical");
    expect(data.hud_color).toBe("red");
    expect(data.trend).toHaveLength(0);
  });

  test("trend is capped at 5 most recent sessions", () => {
    const snapshots = Array.from({ length: 8 }, (_, i) =>
      fakeSnapshot((i + 3) / 10),
    );

    const data = computeReliabilityHudData(snapshots);

    expect(data.trend.length).toBe(5);
  });

  test("drift alerts are passed through", () => {
    const snapshots = [fakeSnapshot(0.5)];
    const alerts = ["Semantic drift detected", "Consensus below threshold"];

    const data = computeReliabilityHudData(snapshots, alerts);

    expect(data.drift_alerts).toEqual(alerts);
  });
});
