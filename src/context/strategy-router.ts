import {
  reconstructWorkspace,
  type WorkspaceReconstructionRequest,
} from "./workspace-reconstruction.js";

export type StrategyName =
  | "keep-last-n"
  | "summarize"
  | "discard-all"
  | "durability";

export const STRATEGY_REGISTRY = [
  "keep-last-n",
  "summarize",
  "discard-all",
  "durability",
] as const;

export interface ContextState {
  readonly totalTokens: number;
  readonly maxTokens: number;
  readonly turnCount: number;
  readonly hasRecentDecisions: boolean;
  readonly hasEvidenceRefs: boolean;
  readonly freshnessScore?: number;
  readonly durabilityContext?: WorkspaceReconstructionRequest;
}

export interface StrategyEvaluation {
  readonly strategy: StrategyName;
  readonly score: number;
  readonly rationale: string;
}

export interface StrategySelectionResult {
  readonly selected: StrategyName;
  readonly evaluations: readonly StrategyEvaluation[];
  readonly pressure: number;
}

const PRESSURE_TRIGGER_THRESHOLD = 0.7;
const EMERGENCY_THRESHOLD = 0.85;
const LOOKAHEAD_STEPS = 3;
const DEFAULT_KEEP_N = 20;
const DURABILITY_FRESHNESS_THRESHOLD = 40;

export function computePressure(state: ContextState): number {
  return state.totalTokens / state.maxTokens;
}

export function shouldTrigger(state: ContextState): boolean {
  return (
    computePressure(state) >= PRESSURE_TRIGGER_THRESHOLD ||
    (state.freshnessScore ?? 100) < DURABILITY_FRESHNESS_THRESHOLD
  );
}

function scoreKeepLastN(
  state: ContextState,
  pressure: number,
): StrategyEvaluation {
  let score = 0.5;
  if (state.hasRecentDecisions) score += 0.2;
  if (pressure < 0.8) score += 0.15;
  if ((state.freshnessScore ?? 100) < DURABILITY_FRESHNESS_THRESHOLD)
    score -= 0.4;
  const projectedPressureAfterN =
    pressure * (DEFAULT_KEEP_N / Math.max(state.turnCount, 1));
  if (projectedPressureAfterN < 0.6) score += 0.1;
  score = Math.max(0, Math.min(1, score));
  return {
    strategy: "keep-last-n",
    score,
    rationale: `Retains last ${DEFAULT_KEEP_N} turns; pressure=${pressure.toFixed(2)}`,
  };
}

function scoreSummarize(
  state: ContextState,
  pressure: number,
): StrategyEvaluation {
  let score = 0.6;
  if (state.hasEvidenceRefs) score += 0.15;
  if (pressure > 0.75 && pressure < EMERGENCY_THRESHOLD) score += 0.1;
  if (state.turnCount > 30) score += 0.1;
  score = Math.max(0, Math.min(1, score));
  return {
    strategy: "summarize",
    score,
    rationale: `Hierarchical summarization; preserves decisions and evidence refs`,
  };
}

function scoreDiscardAll(
  state: ContextState,
  pressure: number,
): StrategyEvaluation {
  let score = 0.3;
  if (pressure >= EMERGENCY_THRESHOLD) score += 0.5;
  if (!state.hasEvidenceRefs && !state.hasRecentDecisions) score += 0.15;
  score = Math.max(0, Math.min(1, score));
  return {
    strategy: "discard-all",
    score,
    rationale: `Full reconstruction from workspace state; last resort for critical pressure`,
  };
}

function scoreDurability(
  state: ContextState,
  pressure: number,
): StrategyEvaluation {
  const freshnessScore = state.freshnessScore ?? 100;
  let score = 0.2;
  if (pressure > PRESSURE_TRIGGER_THRESHOLD) score += 0.25;
  if (freshnessScore < DURABILITY_FRESHNESS_THRESHOLD) {
    score += 0.55;
    score = Math.max(score, 0.98);
  }
  if (pressure > PRESSURE_TRIGGER_THRESHOLD && freshnessScore < 60)
    score += 0.1;
  score = Math.max(0, Math.min(1, score));
  return {
    strategy: "durability",
    score,
    rationale: `Adaptive reconstruction; pressure=${pressure.toFixed(2)} freshness=${freshnessScore.toFixed(0)}`,
  };
}

function applyLookahead(
  evaluations: StrategyEvaluation[],
  _state: ContextState,
  pressure: number,
): StrategyEvaluation[] {
  return evaluations.map((ev) => {
    let projectedPressure = pressure;
    for (let step = 0; step < LOOKAHEAD_STEPS; step++) {
      if (ev.strategy === "keep-last-n") {
        projectedPressure *= 0.6;
      } else if (ev.strategy === "summarize") {
        projectedPressure *= 0.45;
      } else if (ev.strategy === "durability") {
        projectedPressure *= 0.35;
      } else {
        projectedPressure *= 0.2;
      }
    }
    const lookaheadBonus = projectedPressure < 0.5 ? 0.05 : 0;
    return { ...ev, score: Math.min(1, ev.score + lookaheadBonus) };
  });
}

export function evaluateStrategies(
  state: ContextState,
): StrategySelectionResult {
  const pressure = computePressure(state);

  const rawEvaluations: StrategyEvaluation[] = [
    scoreKeepLastN(state, pressure),
    scoreSummarize(state, pressure),
    scoreDiscardAll(state, pressure),
    scoreDurability(state, pressure),
  ];

  const evaluations = applyLookahead(rawEvaluations, state, pressure);
  const sorted = [...evaluations].sort((a, b) => b.score - a.score);
  const selected = sorted[0]?.strategy ?? "summarize";

  return { selected, evaluations: sorted, pressure };
}

export function selectStrategy(
  state: ContextState,
): StrategySelectionResult | null {
  if (!shouldTrigger(state)) return null;
  const result = evaluateStrategies(state);
  if (result.selected === "durability" && state.durabilityContext) {
    void reconstructWorkspace(state.durabilityContext);
  }
  return result;
}
