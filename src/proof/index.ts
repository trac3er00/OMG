import { DIMENSION_WEIGHTS, getProofBand } from "./types.js";
import type {
  DimensionScore,
  ProofDimension,
  ProofInput,
  ProofScore,
} from "./types.js";

const DIMENSION_ORDER: ProofDimension[] = [
  "tests",
  "lint",
  "typecheck",
  "coverage",
  "uiDiff",
];

function roundScore(value: number): number {
  return Number(value.toFixed(2));
}

function getTestsScore(input: ProofInput): number {
  if (input.tests == null) {
    return 0;
  }

  const totalExecuted = input.tests.pass + input.tests.fail;
  if (totalExecuted <= 0) {
    return 0;
  }

  return roundScore(
    (input.tests.pass / totalExecuted) * DIMENSION_WEIGHTS.tests,
  );
}

function getCoverageScore(input: ProofInput): number {
  if (input.coverage == null) {
    return 0;
  }

  const normalizedCoverage = Math.max(0, Math.min(100, input.coverage));
  return roundScore((normalizedCoverage / 100) * DIMENSION_WEIGHTS.coverage);
}

function getBreakdown(input: ProofInput): Record<ProofDimension, number> {
  return {
    tests: getTestsScore(input),
    lint: input.lint === true ? DIMENSION_WEIGHTS.lint : 0,
    typecheck: input.typecheck === true ? DIMENSION_WEIGHTS.typecheck : 0,
    coverage: getCoverageScore(input),
    uiDiff: input.uiDiff === true ? DIMENSION_WEIGHTS.uiDiff : 0,
  };
}

function toDimensionScore(
  dimension: ProofDimension,
  score: number,
): DimensionScore {
  const maxScore = DIMENSION_WEIGHTS[dimension];

  return {
    dimension,
    score,
    maxScore,
    passed: score >= maxScore,
  };
}

export function computeProofScore(input: ProofInput): ProofScore {
  const breakdown = getBreakdown(input);
  const score = roundScore(
    DIMENSION_ORDER.reduce(
      (total, dimension) => total + breakdown[dimension],
      0,
    ),
  );

  return {
    score,
    band: getProofBand(score),
    dimensions: DIMENSION_ORDER.map((dimension) =>
      toDimensionScore(dimension, breakdown[dimension]),
    ),
    breakdown,
  };
}
