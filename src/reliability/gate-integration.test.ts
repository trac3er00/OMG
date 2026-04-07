import { describe, expect, test } from "bun:test";

import {
  evaluateGate,
  DEFAULT_RELIABILITY_THRESHOLD,
} from "./gate-integration";

describe("evaluateGate", () => {
  test("low-score", () => {
    const result = evaluateGate(45, 60);

    expect(result.passed).toBe(false);
    expect(result.score).toBe(45);
    expect(result.threshold).toBe(60);
    expect(result.warning).toBeDefined();
    expect(result.warning).toContain("below threshold");
    expect(result.warning).toContain("45");
    expect(result.warning).toContain("60");
  });

  test("pass", () => {
    const result = evaluateGate(80, 60);

    expect(result.passed).toBe(true);
    expect(result.score).toBe(80);
    expect(result.threshold).toBe(60);
    expect(result.warning).toBeUndefined();
  });

  test("exact threshold passes", () => {
    const result = evaluateGate(60, 60);

    expect(result.passed).toBe(true);
    expect(result.warning).toBeUndefined();
  });

  test("uses default threshold when none provided", () => {
    const result = evaluateGate(50);

    expect(result.threshold).toBe(DEFAULT_RELIABILITY_THRESHOLD);
    expect(result.passed).toBe(false);
  });

  test("zero score fails with warning", () => {
    const result = evaluateGate(0);

    expect(result.passed).toBe(false);
    expect(result.warning).toContain("below threshold");
  });

  test("perfect score passes", () => {
    const result = evaluateGate(100);

    expect(result.passed).toBe(true);
    expect(result.warning).toBeUndefined();
  });
});
