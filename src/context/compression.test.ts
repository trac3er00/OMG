import { describe, test, expect } from "bun:test";
import {
  ADVISORY_THRESHOLD,
  AUTOMATIC_THRESHOLD,
  EMERGENCY_THRESHOLD,
  classifyPressureLevel,
  applyLevel1Compression,
  applyLevel2Compression,
  applyLevel3Compression,
  selectCompressionLevel,
  compress,
} from "./compression.js";
import { type ContextState } from "./strategy-router.js";

const makeState = (total: number, max = 100000): ContextState => ({
  totalTokens: total,
  maxTokens: max,
  turnCount: 20,
  hasRecentDecisions: true,
  hasEvidenceRefs: true,
});

describe("context/compression", () => {
  test("ADVISORY_THRESHOLD is 0.5", () => {
    expect(ADVISORY_THRESHOLD).toBe(0.5);
  });

  test("AUTOMATIC_THRESHOLD is 0.7", () => {
    expect(AUTOMATIC_THRESHOLD).toBe(0.7);
  });

  test("EMERGENCY_THRESHOLD is 0.85", () => {
    expect(EMERGENCY_THRESHOLD).toBe(0.85);
  });

  describe("classifyPressureLevel", () => {
    test("pressure 0.6 → advisory", () => {
      const r = classifyPressureLevel(0.6);
      expect(r.level).toBe("advisory");
      expect(r.action).toBe("suggest");
    });

    test("pressure 0.75 → automatic", () => {
      const r = classifyPressureLevel(0.75);
      expect(r.level).toBe("automatic");
      expect(r.action).toBe("compress");
    });

    test("pressure 0.9 → emergency", () => {
      const r = classifyPressureLevel(0.9);
      expect(r.level).toBe("emergency");
      expect(r.action).toBe("reconstruct");
    });

    test("pressure 0.3 → advisory (below advisory threshold returns advisory)", () => {
      const r = classifyPressureLevel(0.3);
      expect(r.level).toBe("advisory");
    });

    test("threshold boundary: exactly 0.85 → emergency", () => {
      const r = classifyPressureLevel(0.85);
      expect(r.level).toBe("emergency");
    });

    test("threshold boundary: exactly 0.7 → automatic", () => {
      const r = classifyPressureLevel(0.7);
      expect(r.level).toBe("automatic");
    });
  });

  describe("compression levels", () => {
    test("level 1 retains ~85% tokens", () => {
      const result = applyLevel1Compression(100000);
      expect(result.compressed_tokens).toBe(85000);
      expect(result.retention_rate).toBe(0.95);
      expect(result.level).toBe(1);
    });

    test("level 2 retains ~55% tokens", () => {
      const result = applyLevel2Compression(100000);
      expect(result.compressed_tokens).toBe(55000);
      expect(result.retention_rate).toBe(0.82);
      expect(result.level).toBe(2);
    });

    test("level 3 retains ~20% tokens", () => {
      const result = applyLevel3Compression(100000);
      expect(result.compressed_tokens).toBe(20000);
      expect(result.retention_rate).toBe(0.6);
      expect(result.level).toBe(3);
    });

    test("all levels produce reduced token count", () => {
      const tokens = 80000;
      expect(applyLevel1Compression(tokens).compressed_tokens).toBeLessThan(
        tokens,
      );
      expect(applyLevel2Compression(tokens).compressed_tokens).toBeLessThan(
        tokens,
      );
      expect(applyLevel3Compression(tokens).compressed_tokens).toBeLessThan(
        tokens,
      );
    });
  });

  describe("selectCompressionLevel", () => {
    test("low pressure → level 1", () => {
      expect(selectCompressionLevel(0.6)).toBe(1);
    });

    test("medium pressure → level 2", () => {
      expect(selectCompressionLevel(0.75)).toBe(2);
    });

    test("high pressure → level 3", () => {
      expect(selectCompressionLevel(0.9)).toBe(3);
    });
  });

  describe("compress", () => {
    test("compresses high-pressure context", () => {
      const state = makeState(90000);
      const result = compress(state);
      expect(result.compressed_tokens).toBeLessThan(90000);
      expect(result.level).toBe(3);
    });

    test("uses level 2 for medium pressure", () => {
      const state = makeState(75000);
      const result = compress(state);
      expect(result.level).toBe(2);
      expect(result.strategy_used).toBe("summarize");
    });

    test("uses level 1 for low-medium pressure", () => {
      const state = makeState(60000);
      const result = compress(state);
      expect(result.level).toBe(1);
      expect(result.strategy_used).toBe("keep-last-n");
    });

    test("compression result has valid retention rate 0-1", () => {
      const state = makeState(80000);
      const result = compress(state);
      expect(result.retention_rate).toBeGreaterThan(0);
      expect(result.retention_rate).toBeLessThanOrEqual(1);
    });
  });
});
