import { describe, test, expect } from "bun:test";
import {
  DEBATE_VERSION,
  MAX_DEBATE_ROUNDS,
  SOT_COMPLEXITY_THRESHOLD,
  PERSPECTIVE_PROMPTS,
  shouldActivateSoT,
  createPerspectiveOutput,
  hasBlockingDisagreement,
  PerspectiveOutputSchema,
} from "./perspectives.js";

describe("debate/perspectives", () => {
  test("DEBATE_VERSION is 1.0.0", () => {
    expect(DEBATE_VERSION).toBe("1.0.0");
  });

  test("MAX_DEBATE_ROUNDS is 3", () => {
    expect(MAX_DEBATE_ROUNDS).toBe(3);
  });

  test("SOT_COMPLEXITY_THRESHOLD is 3", () => {
    expect(SOT_COMPLEXITY_THRESHOLD).toBe(3);
  });

  describe("PERSPECTIVE_PROMPTS", () => {
    test("all 5 roles have prompts", () => {
      const roles = [
        "proposer",
        "critic",
        "red-team",
        "domain-expert",
        "reconciler",
      ] as const;
      for (const role of roles) {
        expect(typeof PERSPECTIVE_PROMPTS[role]).toBe("string");
        expect(PERSPECTIVE_PROMPTS[role].length).toBeGreaterThan(0);
      }
    });
  });

  describe("shouldActivateSoT", () => {
    test("trivial task (complexity 1) does NOT activate", () => {
      const result = shouldActivateSoT({ complexity_level: 1 });
      expect(result.should_activate).toBe(false);
    });

    test("complex task (complexity 5) DOES activate", () => {
      const result = shouldActivateSoT({ complexity_level: 5 });
      expect(result.should_activate).toBe(true);
    });

    test("high-stakes task activates regardless of complexity", () => {
      const result = shouldActivateSoT({
        complexity_level: 1,
        is_high_stakes: true,
      });
      expect(result.should_activate).toBe(true);
    });

    test("security domain activates even at low complexity", () => {
      const result = shouldActivateSoT({
        complexity_level: 2,
        domain: "security",
      });
      expect(result.should_activate).toBe(true);
    });

    test("unknown domain at low complexity does NOT activate", () => {
      const result = shouldActivateSoT({
        complexity_level: 2,
        domain: "readme-update",
      });
      expect(result.should_activate).toBe(false);
    });

    test("result includes reason string", () => {
      const result = shouldActivateSoT({ complexity_level: 4 });
      expect(typeof result.reason).toBe("string");
      expect(result.reason.length).toBeGreaterThan(0);
    });
  });

  describe("createPerspectiveOutput", () => {
    test("creates valid proposer output", () => {
      const output = createPerspectiveOutput(
        "proposer",
        "Use JWT for authentication",
      );
      expect(output.role).toBe("proposer");
      expect(output.position).toBe("Use JWT for authentication");
      expect(output.round).toBe(1);
    });

    test("creates output with custom confidence", () => {
      const output = createPerspectiveOutput("critic", "Disagree", {
        confidence: 0.9,
      });
      expect(output.confidence).toBe(0.9);
    });

    test("validates against schema", () => {
      const output = createPerspectiveOutput("proposer", "Test position");
      expect(PerspectiveOutputSchema.safeParse(output).success).toBe(true);
    });

    test("creates output with disagreements", () => {
      const output = createPerspectiveOutput("red-team", "Security risk", {
        disagreements: [
          {
            role: "proposer",
            claim: "JWT is safe",
            rationale: "JWT can be compromised",
            severity: "blocking",
            evidence: ["CVE-2022-1234"],
          },
        ],
      });
      expect(output.disagreements.length).toBe(1);
      expect(output.disagreements[0]?.severity).toBe("blocking");
    });
  });

  describe("hasBlockingDisagreement", () => {
    test("returns false when no blocking disagreements", () => {
      const outputs = [
        createPerspectiveOutput("proposer", "Position A"),
        createPerspectiveOutput("critic", "Position B"),
      ];
      expect(hasBlockingDisagreement(outputs)).toBe(false);
    });

    test("returns true when any output has blocking disagreement", () => {
      const outputs = [
        createPerspectiveOutput("red-team", "Security risk", {
          disagreements: [
            {
              role: "proposer",
              claim: "Safe approach",
              rationale: "Not actually safe",
              severity: "blocking",
              evidence: [],
            },
          ],
        }),
      ];
      expect(hasBlockingDisagreement(outputs)).toBe(true);
    });

    test("returns false for minor disagreements", () => {
      const outputs = [
        createPerspectiveOutput("critic", "Minor issue", {
          disagreements: [
            {
              role: "proposer",
              claim: "This works",
              rationale: "Could be better",
              severity: "minor",
              evidence: [],
            },
          ],
        }),
      ];
      expect(hasBlockingDisagreement(outputs)).toBe(false);
    });
  });
});
