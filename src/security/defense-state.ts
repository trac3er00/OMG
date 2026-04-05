import type { RiskLevel } from "../interfaces/policy.js";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";

export interface DefenseScores {
  readonly injectionHits: number;
  readonly contaminationScore: number;
  readonly overthinkingScore: number;
  readonly prematureFixerScore: number;
}

export interface DefenseStateData extends DefenseScores {
  readonly riskLevel: RiskLevel;
  readonly actions: readonly string[];
  readonly reasons: readonly string[];
  readonly updatedAt: string;
}

const DEFAULT_STATE: DefenseStateData = {
  riskLevel: "low",
  injectionHits: 0,
  contaminationScore: 0,
  overthinkingScore: 0,
  prematureFixerScore: 0,
  actions: [],
  reasons: [],
  updatedAt: new Date().toISOString(),
};

/**
 * Compute risk level from defense scores using fixed thresholds.
 *
 * - critical: injectionHits >= 3 OR contaminationScore >= 0.7
 * - high:     injectionHits >= 1 OR contaminationScore >= 0.4
 * - medium:   overthinkingScore >= 0.5 OR prematureFixerScore >= 0.5
 * - low:      everything else
 */
export function computeRiskLevel(scores: DefenseScores): RiskLevel {
  if (scores.injectionHits >= 3 || scores.contaminationScore >= 0.7) {
    return "critical";
  }
  if (scores.injectionHits >= 1 || scores.contaminationScore >= 0.4) {
    return "high";
  }
  if (scores.overthinkingScore >= 0.5 || scores.prematureFixerScore >= 0.5) {
    return "medium";
  }
  return "low";
}

export class DefenseStateManager {
  private readonly statePath: string;

  constructor(projectDir: string) {
    const resolver = new StateResolver(projectDir);
    this.statePath = resolver.layout().defenseState;
  }

  load(): DefenseStateData {
    return readJsonFile<DefenseStateData>(this.statePath) ?? DEFAULT_STATE;
  }

  update(
    input: DefenseScores & {
      actions: readonly string[];
      reasons: readonly string[];
    },
  ): DefenseStateData {
    const riskLevel = computeRiskLevel(input);
    const state: DefenseStateData = {
      injectionHits: input.injectionHits,
      contaminationScore: input.contaminationScore,
      overthinkingScore: input.overthinkingScore,
      prematureFixerScore: input.prematureFixerScore,
      riskLevel,
      actions: [...input.actions],
      reasons: [...input.reasons],
      updatedAt: new Date().toISOString(),
    };
    atomicWriteJson(this.statePath, state);
    return state;
  }

  reset(): void {
    atomicWriteJson(this.statePath, {
      ...DEFAULT_STATE,
      updatedAt: new Date().toISOString(),
    });
  }
}
