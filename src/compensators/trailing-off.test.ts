import { describe, expect, it } from "bun:test";

import { detectTrailingOff, type TaskItem } from "./trailing-off";

function createItems(lineCounts: number[]): TaskItem[] {
  return lineCounts.map((lineCount, index) => ({
    id: `item-${index + 1}`,
    content: `Task content ${index + 1}`,
    lineCount,
  }));
}

describe("detectTrailingOff", () => {
  it("returns detected false for fewer than five items", () => {
    const result = detectTrailingOff(createItems([50, 45, 55]));

    expect(result.detected).toBe(false);
    expect(result.qualityRatio).toBe(1);
    expect(result.firstGroupAvg).toBe(0);
    expect(result.lastGroupAvg).toBe(0);
    expect(result.correctionMessage).toBeUndefined();
  });

  it("detects quality drop when later items are much shorter", () => {
    const result = detectTrailingOff(createItems([50, 50, 50, 50, 50, 50, 5, 5, 5]));

    expect(result.detected).toBe(true);
    expect(result.qualityRatio).toBeCloseTo(0.1, 5);
  });

  it("does not detect trailing off when quality is consistent", () => {
    const result = detectTrailingOff(createItems([50, 52, 49, 51, 50, 48, 53, 50, 49]));

    expect(result.detected).toBe(false);
    expect(result.qualityRatio).toBeGreaterThanOrEqual(0.7);
  });

  it("has qualityRatio below 0.3 for extreme trailing off", () => {
    const result = detectTrailingOff(createItems([50, 50, 50, 50, 50, 50, 5, 5, 5]));

    expect(result.qualityRatio).toBeLessThan(0.3);
  });

  it("sets correctionMessage only when trailing off is detected", () => {
    const detectedResult = detectTrailingOff(createItems([50, 50, 50, 50, 50, 50, 5, 5, 5]));
    const cleanResult = detectTrailingOff(createItems([50, 50, 50, 50, 50, 50, 50, 50, 50]));

    expect(detectedResult.correctionMessage).toBeDefined();
    expect(cleanResult.correctionMessage).toBeUndefined();
  });

  it("works with exactly five items", () => {
    const result = detectTrailingOff(createItems([50, 50, 50, 5, 5]));

    expect(result.detected).toBe(true);
    expect(result.qualityRatio).toBeCloseTo(0.1, 5);
  });
});
