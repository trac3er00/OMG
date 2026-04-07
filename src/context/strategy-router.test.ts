import { describe, test, expect } from "bun:test";
import {
  STRATEGY_REGISTRY,
  computePressure,
  shouldTrigger,
  evaluateStrategies,
  selectStrategy,
  type ContextState,
} from "./strategy-router.js";

const baseState: ContextState = {
  totalTokens: 50000,
  maxTokens: 100000,
  turnCount: 25,
  hasRecentDecisions: true,
  hasEvidenceRefs: true,
  freshnessScore: 85,
};

describe("context/strategy-router", () => {
  test("durability strategy is registered", () => {
    expect(STRATEGY_REGISTRY).toContain("durability");
  });

  describe("computePressure", () => {
    test("returns ratio of used to max tokens", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 70000,
        maxTokens: 100000,
      };
      expect(computePressure(state)).toBe(0.7);
    });

    test("returns 0 for empty context", () => {
      expect(computePressure({ ...baseState, totalTokens: 0 })).toBe(0);
    });

    test("returns 1.0 for full context", () => {
      expect(
        computePressure({
          ...baseState,
          totalTokens: 100000,
          maxTokens: 100000,
        }),
      ).toBe(1.0);
    });
  });

  describe("shouldTrigger", () => {
    test("triggers at pressure 0.8 (above 0.7 threshold)", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 80000,
        maxTokens: 100000,
      };
      expect(shouldTrigger(state)).toBe(true);
    });

    test("does not trigger at pressure 0.3", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 30000,
        maxTokens: 100000,
      };
      expect(shouldTrigger(state)).toBe(false);
    });

    test("triggers exactly at threshold 0.7", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 70000,
        maxTokens: 100000,
      };
      expect(shouldTrigger(state)).toBe(true);
    });

    test("does not trigger just below threshold", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 69000,
        maxTokens: 100000,
      };
      expect(shouldTrigger(state)).toBe(false);
    });

    test("triggers durability when freshness score decays below 40", () => {
      expect(
        shouldTrigger({
          ...baseState,
          totalTokens: 30000,
          freshnessScore: 35,
        }),
      ).toBe(true);
    });
  });

  describe("evaluateStrategies", () => {
    test("returns all registered strategies including durability", () => {
      const result = evaluateStrategies({ ...baseState, totalTokens: 80000 });
      const names = result.evaluations.map((e) => e.strategy);
      expect(names).toContain("keep-last-n");
      expect(names).toContain("summarize");
      expect(names).toContain("discard-all");
      expect(names).toContain("durability");
    });

    test("all scores are numeric 0-1", () => {
      const result = evaluateStrategies(baseState);
      for (const ev of result.evaluations) {
        expect(ev.score).toBeGreaterThanOrEqual(0);
        expect(ev.score).toBeLessThanOrEqual(1);
      }
    });

    test("returns pressure value", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 80000,
        maxTokens: 100000,
      };
      const result = evaluateStrategies(state);
      expect(result.pressure).toBeCloseTo(0.8, 5);
    });

    test("selected strategy has highest score", () => {
      const result = evaluateStrategies({ ...baseState, totalTokens: 80000 });
      const winnerScore =
        result.evaluations.find((e) => e.strategy === result.selected)?.score ??
        0;
      for (const ev of result.evaluations) {
        expect(winnerScore).toBeGreaterThanOrEqual(ev.score);
      }
    });

    test("selection is deterministic (same state → same strategy)", () => {
      const state: ContextState = { ...baseState, totalTokens: 80000 };
      const r1 = evaluateStrategies(state);
      const r2 = evaluateStrategies(state);
      const r3 = evaluateStrategies(state);
      expect(r1.selected).toBe(r2.selected);
      expect(r2.selected).toBe(r3.selected);
    });

    test("emergency pressure (>0.85) selects discard-all or summarize", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 92000,
        maxTokens: 100000,
        hasRecentDecisions: false,
        hasEvidenceRefs: false,
      };
      const result = evaluateStrategies(state);
      expect(["discard-all", "summarize"]).toContain(result.selected);
    });

    test("low-pressure state favors keep-last-n or summarize", () => {
      const state: ContextState = {
        ...baseState,
        totalTokens: 75000,
        maxTokens: 100000,
        hasRecentDecisions: true,
        hasEvidenceRefs: true,
      };
      const result = evaluateStrategies(state);
      expect(["keep-last-n", "summarize", "durability"]).toContain(
        result.selected,
      );
    });

    test("durability strategy activates when context pressure exceeds 0.7", () => {
      const result = evaluateStrategies({
        ...baseState,
        totalTokens: 90000,
        freshnessScore: 30,
      });
      const durability = result.evaluations.find(
        (evaluation) => evaluation.strategy === "durability",
      );
      expect(durability).toBeDefined();
      expect(durability?.score).toBeGreaterThan(0.5);
    });

    test("durability strategy wins when freshness is critically low", () => {
      const result = evaluateStrategies({
        ...baseState,
        totalTokens: 30000,
        freshnessScore: 20,
      });
      expect(result.selected).toBe("durability");
    });

    test("each evaluation has a rationale string", () => {
      const result = evaluateStrategies(baseState);
      for (const ev of result.evaluations) {
        expect(typeof ev.rationale).toBe("string");
        expect(ev.rationale.length).toBeGreaterThan(0);
      }
    });
  });

  describe("selectStrategy", () => {
    test("returns null when pressure below threshold", () => {
      const state: ContextState = { ...baseState, totalTokens: 30000 };
      expect(selectStrategy(state)).toBeNull();
    });

    test("returns result when pressure above threshold", () => {
      const state: ContextState = { ...baseState, totalTokens: 80000 };
      const result = selectStrategy(state);
      expect(result).not.toBeNull();
      expect(result?.selected).toBeDefined();
    });

    test("4 evaluations returned when triggered", () => {
      const state: ContextState = { ...baseState, totalTokens: 80000 };
      const result = selectStrategy(state);
      expect(result?.evaluations.length).toBe(4);
    });
  });
});
