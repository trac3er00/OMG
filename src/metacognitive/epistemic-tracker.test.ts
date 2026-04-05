import { describe, test, expect } from "bun:test";
import {
  KNOWN_DOMAINS,
  assessEpistemicState,
  trackNovelDomain,
  mergeAssessments,
} from "./epistemic-tracker.js";

describe("metacognitive/epistemic-tracker", () => {
  describe("KNOWN_DOMAINS", () => {
    test("typescript is a known domain", () => {
      expect(KNOWN_DOMAINS.has("typescript")).toBe(true);
    });

    test("robotics is NOT a known domain (triggers novel domain flag)", () => {
      expect(KNOWN_DOMAINS.has("robotics")).toBe(false);
    });
  });

  describe("assessEpistemicState", () => {
    test("high confidence + evidence → KNOWN", () => {
      const result = assessEpistemicState({
        confidence: 0.95,
        source: "claim_judge",
        domain: "typescript",
        evidence_refs: ["test.json"],
      });
      expect(result.state.classification).toBe("known");
      expect(result.uncertainty_score.value).toBe(0.95);
    });

    test("low confidence + no evidence → UNKNOWN", () => {
      const result = assessEpistemicState({
        confidence: 0.2,
        source: "claim_judge",
        evidence_refs: [],
      });
      expect(result.state.classification).toBe("unknown");
    });

    test("medium confidence → UNCERTAIN", () => {
      const result = assessEpistemicState({
        confidence: 0.5,
        source: "evidence_count",
        evidence_refs: ["partial.json"],
      });
      expect(result.state.classification).toBe("uncertain");
    });

    test("novel domain triggers unknown_unknowns flag", () => {
      const result = assessEpistemicState({
        confidence: 0.9,
        source: "claim_judge",
        domain: "quantum-computing",
        evidence_refs: ["qc.json"],
      });
      expect(result.novel_domain).toBe(true);
      expect(result.state.unknown_unknowns_detected).toBe(true);
      expect(result.flags.some((f) => f.includes("novel_domain"))).toBe(true);
    });

    test("known domain does NOT trigger novel_domain", () => {
      const result = assessEpistemicState({
        confidence: 0.9,
        source: "claim_judge",
        domain: "typescript",
        evidence_refs: ["ts.json"],
      });
      expect(result.novel_domain).toBe(false);
    });

    test("no evidence adds no_evidence flag", () => {
      const result = assessEpistemicState({
        confidence: 0.8,
        source: "fallback",
        evidence_refs: [],
      });
      expect(result.flags).toContain("no_evidence");
    });
  });

  describe("trackNovelDomain", () => {
    test("novel domain with 0 evidence → low confidence", () => {
      const result = trackNovelDomain("embedded-systems", 0);
      expect(result.uncertainty_score.value).toBe(0.1);
      expect(result.novel_domain).toBe(true);
    });

    test("novel domain with some evidence → higher confidence", () => {
      const result = trackNovelDomain("embedded-systems", 3);
      expect(result.uncertainty_score.value).toBeGreaterThan(0.1);
      expect(result.uncertainty_score.value).toBeLessThanOrEqual(0.6);
    });
  });

  describe("mergeAssessments", () => {
    test("empty array returns low-confidence unknown", () => {
      const result = mergeAssessments([]);
      expect(result.uncertainty_score.value).toBe(0);
    });

    test("merges confidence as average", () => {
      const a1 = assessEpistemicState({
        confidence: 0.8,
        source: "claim_judge",
        evidence_refs: ["a.json"],
      });
      const a2 = assessEpistemicState({
        confidence: 0.6,
        source: "evidence_count",
        evidence_refs: ["b.json"],
      });
      const merged = mergeAssessments([a1, a2]);
      expect(merged.uncertainty_score.value).toBeCloseTo(0.7, 5);
    });

    test("novel domain in any assessment propagates to merged", () => {
      const a1 = assessEpistemicState({
        confidence: 0.9,
        source: "claim_judge",
        domain: "typescript",
        evidence_refs: ["a.json"],
      });
      const a2 = assessEpistemicState({
        confidence: 0.5,
        source: "fallback",
        domain: "robotics",
        evidence_refs: [],
      });
      const merged = mergeAssessments([a1, a2]);
      expect(merged.novel_domain).toBe(true);
    });

    test("deduplicates evidence refs", () => {
      const a1 = assessEpistemicState({
        confidence: 0.8,
        source: "claim_judge",
        evidence_refs: ["a.json", "b.json"],
      });
      const a2 = assessEpistemicState({
        confidence: 0.8,
        source: "claim_judge",
        evidence_refs: ["b.json", "c.json"],
      });
      const merged = mergeAssessments([a1, a2]);
      const refs = merged.state.evidence_refs;
      const uniqueRefs = new Set(refs);
      expect(uniqueRefs.size).toBe(refs.length);
    });
  });
});
