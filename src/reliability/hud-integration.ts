import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

import {
  ReliabilitySnapshotSchema,
  type ReliabilitySnapshot,
} from "./metrics.js";

export interface ReliabilityHudData {
  reliability_score: number;
  reliability_band: "critical" | "low" | "medium" | "high";
  hud_color: "red" | "orange" | "yellow" | "green";
  trend: Array<{ session: string; score: number }>;
  drift_alerts: string[];
}

/** Critical (0-25) → red, Low (26-50) → orange, Medium (51-75) → yellow, High (76-100) → green */
export function scoreToHudColor(
  score: number,
): "red" | "orange" | "yellow" | "green" {
  if (score <= 25) return "red";
  if (score <= 50) return "orange";
  if (score <= 75) return "yellow";
  return "green";
}

/** Critical (0-25), Low (26-50), Medium (51-75), High (76-100) */
export function scoreToHudBand(
  score: number,
): "critical" | "low" | "medium" | "high" {
  if (score <= 25) return "critical";
  if (score <= 50) return "low";
  if (score <= 75) return "medium";
  return "high";
}

export function computeReliabilityHudData(
  snapshots: readonly ReliabilitySnapshot[],
  driftAlerts: readonly string[] = [],
): ReliabilityHudData {
  const latest =
    snapshots.length > 0 ? snapshots[snapshots.length - 1] : undefined;
  const reliability_score = latest ? Math.round(latest.overall_score * 100) : 0;

  const recent = snapshots.slice(-5);
  const trend = recent.map((s) => ({
    session: s.snapshot_id,
    score: Math.round(s.overall_score * 100),
  }));

  return {
    reliability_score,
    reliability_band: scoreToHudBand(reliability_score),
    hud_color: scoreToHudColor(reliability_score),
    trend,
    drift_alerts: [...driftAlerts],
  };
}

export async function getReliabilityHudData(
  projectDir = ".",
): Promise<ReliabilityHudData> {
  const historyPath = join(projectDir, ".omg", "reliability", "history.jsonl");

  const snapshots: ReliabilitySnapshot[] = [];
  if (existsSync(historyPath)) {
    const lines = readFileSync(historyPath, "utf-8")
      .split("\n")
      .filter((line) => line.trim());

    for (const line of lines) {
      try {
        const parsed = ReliabilitySnapshotSchema.parse(JSON.parse(line));
        snapshots.push(parsed);
      } catch {
        continue;
      }
    }
  }

  const driftAlerts: string[] = [];
  if (snapshots.length > 0) {
    const latest = snapshots[snapshots.length - 1];
    for (const metric of latest.metrics) {
      if (metric.status === "fail") {
        driftAlerts.push(
          `${metric.name} below threshold (${(metric.score * 100).toFixed(0)}% < ${(metric.threshold * 100).toFixed(0)}%)`,
        );
      }
    }
  }

  return computeReliabilityHudData(snapshots, driftAlerts);
}
