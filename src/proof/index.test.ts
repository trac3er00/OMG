import { describe, expect, it } from "bun:test";

import { computeProofScore } from "./index";
import { DIMENSION_WEIGHTS, getProofBand, type DimensionScore } from "./types";

describe("computeProofScore", () => {
  it("returns a perfect score when all dimensions pass", () => {
    const result = computeProofScore({
      tests: { pass: 10, fail: 0 },
      lint: true,
      typecheck: true,
      coverage: 100,
      uiDiff: true,
    });

    expect(result.score).toBe(100);
    expect(result.band).toBe("complete");
    expect(result.breakdown).toEqual({
      tests: 30,
      lint: 15,
      typecheck: 20,
      coverage: 20,
      uiDiff: 15,
    });
    expect(result.dimensions).toEqual([
      {
        dimension: "tests",
        score: 30,
        maxScore: DIMENSION_WEIGHTS.tests,
        passed: true,
      },
      {
        dimension: "lint",
        score: 15,
        maxScore: DIMENSION_WEIGHTS.lint,
        passed: true,
      },
      {
        dimension: "typecheck",
        score: 20,
        maxScore: DIMENSION_WEIGHTS.typecheck,
        passed: true,
      },
      {
        dimension: "coverage",
        score: 20,
        maxScore: DIMENSION_WEIGHTS.coverage,
        passed: true,
      },
      {
        dimension: "uiDiff",
        score: 15,
        maxScore: DIMENSION_WEIGHTS.uiDiff,
        passed: true,
      },
    ]);
  });

  it("penalizes failing tests and stays below 50 total score", () => {
    const result = computeProofScore({ tests: { pass: 5, fail: 5 } });

    expect(result.breakdown.tests).toBe(15);
    expect(result.score).toBeLessThan(50);
    expect(result.band).toBe("weak");
  });

  it("returns zero score for empty input", () => {
    const result = computeProofScore({});

    expect(result.score).toBe(0);
    expect(result.band).toBe("weak");
    expect(result.breakdown).toEqual({
      tests: 0,
      lint: 0,
      typecheck: 0,
      coverage: 0,
      uiDiff: 0,
    });
    expect(result.dimensions).toHaveLength(5);
    expect(
      result.dimensions.every(
        (dimension: DimensionScore) => dimension.score === 0,
      ),
    ).toBe(true);
  });

  it("scores partial lint and typecheck inputs", () => {
    const result = computeProofScore({ lint: true, typecheck: true });

    expect(result.score).toBe(35);
    expect(result.band).toBe(getProofBand(35));
    expect(result.band).toBe("weak");
  });

  it("scales coverage score from percentage", () => {
    const result = computeProofScore({ coverage: 80 });

    expect(result.breakdown.coverage).toBe(16);
    expect(result.score).toBe(16);
  });

  it("ignores skipped tests when computing the pass ratio", () => {
    const result = computeProofScore({ tests: { pass: 8, fail: 0, skip: 2 } });

    expect(result.breakdown.tests).toBe(30);
    expect(result.score).toBe(30);
  });

  it("scores the high-confidence example from the configured weights", () => {
    const result = computeProofScore({
      tests: { pass: 10, fail: 0 },
      lint: true,
      typecheck: true,
      coverage: 85,
    });

    expect(result.score).toBe(82);
    expect(result.band).toBe("strong");
  });
});
