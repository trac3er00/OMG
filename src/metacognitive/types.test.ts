import { describe, test, expect } from "bun:test";
import {
  METACOGNITIVE_VERSION,
  UNCERTAINTY_THRESHOLD,
  createUncertaintyScore,
  createEpistemicState,
  shouldTriggerVerification,
  UncertaintyScoreSchema,
  EpistemicStateSchema,
  MetacognitiveReportSchema,
} from "./types.js";

describe("metacognitive/types", () => {
  test("METACOGNITIVE_VERSION is defined", () => {
    expect(METACOGNITIVE_VERSION).toBe("1.0.0");
  });

  test("UNCERTAINTY_THRESHOLD is 0.7", () => {
    expect(UNCERTAINTY_THRESHOLD).toBe(0.7);
  });

  describe("UncertaintyScore", () => {
    test("valid score 0.0-1.0 passes", () => {
      expect(
        UncertaintyScoreSchema.safeParse({ value: 0.5, source: "claim_judge" })
          .success,
      ).toBe(true);
    });

    test("score below 0 fails", () => {
      expect(
        UncertaintyScoreSchema.safeParse({ value: -0.1, source: "claim_judge" })
          .success,
      ).toBe(false);
    });

    test("score above 1 fails", () => {
      expect(
        UncertaintyScoreSchema.safeParse({ value: 1.1, source: "claim_judge" })
          .success,
      ).toBe(false);
    });

    test("invalid source enum fails", () => {
      expect(
        UncertaintyScoreSchema.safeParse({
          value: 0.5,
          source: "invalid_source",
        }).success,
      ).toBe(false);
    });

    test("all valid sources accepted", () => {
      const sources = [
        "claim_judge",
        "evidence_count",
        "epistemic_state",
        "voting",
        "fallback",
      ] as const;
      for (const source of sources) {
        expect(
          UncertaintyScoreSchema.safeParse({ value: 0.5, source }).success,
        ).toBe(true);
      }
    });
  });

  describe("EpistemicState", () => {
    test("known classification accepted", () => {
      const result = EpistemicStateSchema.safeParse({
        classification: "known",
        evidence_refs: ["test.json"],
        unknown_unknowns_detected: false,
        flags: [],
      });
      expect(result.success).toBe(true);
    });

    test("unknown classification accepted", () => {
      const result = EpistemicStateSchema.safeParse({
        classification: "unknown",
        evidence_refs: [],
        unknown_unknowns_detected: true,
        flags: ["novel_domain"],
      });
      expect(result.success).toBe(true);
    });

    test("invalid classification rejected", () => {
      expect(
        EpistemicStateSchema.safeParse({
          classification: "MAYBE",
          evidence_refs: [],
          unknown_unknowns_detected: false,
          flags: [],
        }).success,
      ).toBe(false);
    });
  });

  describe("createUncertaintyScore", () => {
    test("clamps value above 1 to 1", () => {
      const score = createUncertaintyScore(1.5, "fallback");
      expect(score.value).toBe(1);
    });

    test("clamps value below 0 to 0", () => {
      const score = createUncertaintyScore(-0.5, "fallback");
      expect(score.value).toBe(0);
    });

    test("preserves valid values", () => {
      const score = createUncertaintyScore(0.7, "evidence_count");
      expect(score.value).toBe(0.7);
      expect(score.source).toBe("evidence_count");
    });
  });

  describe("shouldTriggerVerification", () => {
    test("triggers when confidence below threshold", () => {
      const score = createUncertaintyScore(0.5, "claim_judge");
      expect(shouldTriggerVerification(score)).toBe(true);
    });

    test("does NOT trigger when confidence above threshold", () => {
      const score = createUncertaintyScore(0.95, "claim_judge");
      expect(shouldTriggerVerification(score)).toBe(false);
    });

    test("threshold boundary: exactly 0.7 does NOT trigger", () => {
      const score = createUncertaintyScore(0.7, "voting");
      expect(shouldTriggerVerification(score)).toBe(false);
    });
  });

  describe("MetacognitiveReport", () => {
    test("valid full report passes schema", () => {
      const report = {
        schema_version: "1.0.0",
        uncertainty_score: { value: 0.8, source: "claim_judge" },
        epistemic_state: {
          classification: "known",
          evidence_refs: ["proof-gate.json"],
          unknown_unknowns_detected: false,
          flags: [],
        },
        verification_triggered: false,
        final_confidence: 0.9,
        human_auditable_evidence: ["proof-gate.json"],
        generated_at: new Date().toISOString(),
      };
      expect(MetacognitiveReportSchema.safeParse(report).success).toBe(true);
    });

    test("report with wrong schema_version fails", () => {
      const report = {
        schema_version: "2.0.0",
        uncertainty_score: { value: 0.8, source: "claim_judge" },
        epistemic_state: {
          classification: "known",
          evidence_refs: [],
          unknown_unknowns_detected: false,
          flags: [],
        },
        verification_triggered: false,
        final_confidence: 0.9,
        human_auditable_evidence: [],
        generated_at: new Date().toISOString(),
      };
      expect(MetacognitiveReportSchema.safeParse(report).success).toBe(false);
    });
  });

  describe("createEpistemicState", () => {
    test("creates known state with defaults", () => {
      const state = createEpistemicState("known");
      expect(state.classification).toBe("known");
      expect(state.evidence_refs).toEqual([]);
      expect(state.unknown_unknowns_detected).toBe(false);
    });

    test("creates uncertain state with custom domain", () => {
      const state = createEpistemicState("uncertain", { domain: "robotics" });
      expect(state.classification).toBe("uncertain");
      expect(state.domain).toBe("robotics");
    });
  });
});
