/**
 * ProofScore Types and Interfaces
 *
 * Extended proof system with 5 dimensions:
 * - tests: Test pass/fail/skip counts (weight: 30)
 * - lint: Linter pass/fail (weight: 15)
 * - typecheck: TypeScript type checking (weight: 20)
 * - coverage: Code coverage percentage (weight: 20)
 * - uiDiff: UI screenshot diff verification (weight: 15)
 */

/** The 5 proof dimensions */
export type ProofDimension =
  | "tests"
  | "lint"
  | "typecheck"
  | "coverage"
  | "uiDiff";

/** Band classification for a ProofScore */
export type ProofBand = "weak" | "developing" | "strong" | "complete";

/**
 * Input data for computing a ProofScore
 * Each dimension is optional; undefined dimensions contribute 0 score
 */
export interface ProofInput {
  /** Test results: pass/fail counts and optional skips */
  tests?: { pass: number; fail: number; skip?: number };
  /** Linter result: true = no errors */
  lint?: boolean;
  /** TypeScript type check: true = no errors */
  typecheck?: boolean;
  /** Code coverage percentage: 0-100 */
  coverage?: number;
  /** UI diff: true = screenshot captured and matches */
  uiDiff?: boolean;
}

/**
 * Breakdown score for a single dimension
 */
export interface DimensionScore {
  /** Which dimension this score is for */
  dimension: ProofDimension;
  /** Actual score achieved (0 to maxScore) */
  score: number;
  /** Maximum possible score for this dimension */
  maxScore: number;
  /** Whether this dimension passed its threshold */
  passed: boolean;
}

/**
 * Full ProofScore result with all dimensions
 */
export interface ProofScore {
  /** Total score 0-100 */
  score: number;
  /** Band classification */
  band: ProofBand;
  /** Per-dimension breakdown */
  dimensions: DimensionScore[];
  /** Raw scores per dimension */
  breakdown: Record<ProofDimension, number>;
}

/**
 * Dimension weights for the 5 proof dimensions
 * Weights sum to 100
 */
export const DIMENSION_WEIGHTS: Record<ProofDimension, number> = {
  tests: 30,
  lint: 15,
  typecheck: 20,
  coverage: 20,
  uiDiff: 15,
};

/**
 * Convert a numeric score to a ProofBand
 *
 * Band thresholds:
 * - weak: score < 40
 * - developing: 40 <= score < 70
 * - strong: 70 <= score < 90
 * - complete: score >= 90
 *
 * @param score - Numeric score (0-100)
 * @returns The corresponding ProofBand
 */
export function getProofBand(score: number): ProofBand {
  if (score >= 90) {
    return "complete";
  }
  if (score >= 70) {
    return "strong";
  }
  if (score >= 40) {
    return "developing";
  }
  return "weak";
}
