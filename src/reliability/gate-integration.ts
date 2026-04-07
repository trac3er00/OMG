import { getReliabilityHudData } from "./hud-integration.js";

export interface GateResult {
  passed: boolean;
  warning?: string;
  score: number;
  threshold: number;
}

export const DEFAULT_RELIABILITY_THRESHOLD = 60;

export function evaluateGate(
  score: number,
  threshold = DEFAULT_RELIABILITY_THRESHOLD,
): GateResult {
  const passed = score >= threshold;
  const result: GateResult = { passed, score, threshold };
  if (!passed) {
    result.warning = `Reliability score ${score} is below threshold ${threshold}. Consider reviewing recent session reliability.`;
  }
  return result;
}

export async function checkReliabilityGate(
  threshold = DEFAULT_RELIABILITY_THRESHOLD,
  projectDir = ".",
): Promise<GateResult> {
  const hudData = await getReliabilityHudData(projectDir);
  return evaluateGate(hudData.reliability_score, threshold);
}
