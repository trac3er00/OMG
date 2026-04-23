import { describe, it, expect } from "bun:test";
import {
  isTaskIntent,
  isTaskRisk,
  isTaskComplexity,
  isClassificationResult,
} from "./types";

describe("TaskClassifier Types", () => {
  describe("isTaskIntent", () => {
    it("returns true for valid intent 'build'", () => {
      expect(isTaskIntent("build")).toBe(true);
    });

    it("returns true for all valid intents", () => {
      const validIntents = [
        "build",
        "modify",
        "refactor",
        "investigate",
        "deploy",
        "secure",
        "handoff",
      ] as const;
      for (const intent of validIntents) {
        expect(isTaskIntent(intent)).toBe(true);
      }
    });

    it("returns false for invalid intent 'invalid'", () => {
      expect(isTaskIntent("invalid")).toBe(false);
    });

    it("returns false for non-string values", () => {
      expect(isTaskIntent(123)).toBe(false);
      expect(isTaskIntent(null)).toBe(false);
      expect(isTaskIntent(undefined)).toBe(false);
      expect(isTaskIntent({})).toBe(false);
    });
  });

  describe("isTaskRisk", () => {
    it("returns true for valid risk 'critical'", () => {
      expect(isTaskRisk("critical")).toBe(true);
    });

    it("returns true for all valid risks", () => {
      const validRisks = ["low", "medium", "high", "critical"] as const;
      for (const risk of validRisks) {
        expect(isTaskRisk(risk)).toBe(true);
      }
    });

    it("returns false for invalid risk", () => {
      expect(isTaskRisk("extreme")).toBe(false);
    });
  });

  describe("isTaskComplexity", () => {
    it("returns true for all valid complexities", () => {
      const validComplexities = [
        "simple",
        "moderate",
        "hard",
        "expert",
      ] as const;
      for (const complexity of validComplexities) {
        expect(isTaskComplexity(complexity)).toBe(true);
      }
    });

    it("returns false for invalid complexity", () => {
      expect(isTaskComplexity("impossible")).toBe(false);
    });
  });

  describe("isClassificationResult", () => {
    it("returns true for valid ClassificationResult", () => {
      const result = {
        intent: "build",
        risk: "low",
        complexity: "simple",
        confidence: 0.9,
        signals: [],
      };
      expect(isClassificationResult(result)).toBe(true);
    });

    it("returns true for valid ClassificationResult with reasoning", () => {
      const result = {
        intent: "build",
        risk: "low",
        complexity: "simple",
        confidence: 0.9,
        signals: ["signal1", "signal2"],
        reasoning: "Task matches build pattern",
      };
      expect(isClassificationResult(result)).toBe(true);
    });

    it("returns false for empty object", () => {
      expect(isClassificationResult({})).toBe(false);
    });

    it("returns false for null", () => {
      expect(isClassificationResult(null)).toBe(false);
    });

    it("returns false when confidence out of range", () => {
      const result = {
        intent: "build",
        risk: "low",
        complexity: "simple",
        confidence: 1.5,
        signals: [],
      };
      expect(isClassificationResult(result)).toBe(false);
    });

    it("returns false when signals is not an array", () => {
      const result = {
        intent: "build",
        risk: "low",
        complexity: "simple",
        confidence: 0.9,
        signals: "not-an-array",
      };
      expect(isClassificationResult(result)).toBe(false);
    });

    it("returns false for missing required fields", () => {
      const result = {
        intent: "build",
        risk: "low",
        complexity: "simple",
        // missing confidence and signals
      };
      expect(isClassificationResult(result)).toBe(false);
    });

    it("returns false for invalid intent type", () => {
      const result = {
        intent: "invalid",
        risk: "low",
        complexity: "simple",
        confidence: 0.9,
        signals: [],
      };
      expect(isClassificationResult(result)).toBe(false);
    });
  });
});
