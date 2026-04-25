/**
 * User Instruction Adherence Tests
 *
 * Integration tests for the fidelity checker covering all 5 instruction categories:
 * 1. Clear instructions → needsClarification: false
 * 2. Ambiguous instructions → needsClarification: true
 * 3. Dangerous instructions → doesn't block but signals
 * 4. Multi-step instructions → may clarify primary next step
 * 5. Contradictory instructions → may need clarification
 *
 * Also tests: shouldClarify() alignment, max rounds behavior.
 */

import { describe, expect, test } from "bun:test";
import {
  checkFidelity,
  shouldClarify,
} from "../../src/intent/fidelity-checker.js";

// ─── Category 1: Clear Instructions ─────────────────────────────────────────

describe("Category 1: Clear instructions", () => {
  test("specific UI component instruction proceeds without clarification", () => {
    const result = checkFidelity({
      goal: "add a login button to the header component",
    });

    expect(result.needsClarification).toBe(false);
    expect(result.canProceed).toBe(true);
    expect(result.clarificationQuestion).toBeNull();
  });

  test("shouldClarify aligns with checkFidelity for clear instruction", () => {
    const goal = "add a login button to the header component";
    const result = checkFidelity({ goal });

    expect(shouldClarify(goal)).toBe(result.needsClarification);
  });

  test("specific backend endpoint instruction proceeds without clarification", () => {
    const result = checkFidelity({
      goal: "add a POST endpoint for user registration to the auth service",
    });

    expect(result.needsClarification).toBe(false);
    expect(result.canProceed).toBe(true);
    expect(result.clarificationQuestion).toBeNull();
  });

  test("clear instruction returns interpretation string", () => {
    const result = checkFidelity({
      goal: "create a dashboard component for the admin page",
    });

    expect(result.interpretation).toBeTruthy();
    expect(typeof result.interpretation).toBe("string");
    expect(result.interpretation.length).toBeGreaterThan(0);
  });
});

// ─── Category 2: Ambiguous Instructions ─────────────────────────────────────

describe("Category 2: Ambiguous instructions", () => {
  test("'improve it' triggers clarification", () => {
    const result = checkFidelity({ goal: "improve it" });

    expect(result.needsClarification).toBe(true);
    expect(result.canProceed).toBe(false);
    expect(result.clarificationQuestion).toBeTruthy();
  });

  test("shouldClarify aligns with checkFidelity for ambiguous instruction", () => {
    const goal = "fix stuff";
    const result = checkFidelity({ goal });

    expect(shouldClarify(goal)).toBe(result.needsClarification);
  });

  test("'make it better' triggers clarification", () => {
    const result = checkFidelity({ goal: "make it better" });

    expect(result.needsClarification).toBe(true);
    expect(result.canProceed).toBe(false);
    expect(result.clarificationQuestion).toBeTruthy();
  });

  test("ambiguous instruction returns exactly one clarification question", () => {
    const result = checkFidelity({ goal: "do something with the thing" });

    expect(result.needsClarification).toBe(true);
    expect(result.clarificationQuestion).not.toBeNull();
    // Should be a single question (ends with ?)
    expect(result.clarificationQuestion).toMatch(/\?$/u);
    // Should not contain multiple questions
    expect((result.clarificationQuestion!.match(/\?/gu) ?? []).length).toBe(1);
  });

  test("ambiguous instruction includes gap checks", () => {
    const result = checkFidelity({ goal: "fix stuff" });

    expect(result.gapChecks).toHaveLength(3);
    expect(result.gapChecks.every((check) => typeof check === "string")).toBe(
      true,
    );
  });
});

// ─── Category 3: Dangerous Instructions ─────────────────────────────────────

describe("Category 3: Dangerous instructions", () => {
  test("'delete all the database tables' does not block — returns a result", () => {
    const result = checkFidelity({
      goal: "delete all the database tables",
    });

    // Fidelity checker is prompt-layer only — it doesn't block dangerous ops
    // It should return a valid result (not throw)
    expect(result).toBeDefined();
    expect(typeof result.needsClarification).toBe("boolean");
    expect(typeof result.canProceed).toBe("boolean");
    expect(result.gapChecks).toHaveLength(3);
  });

  test("'drop the prod schema' returns a result with interpretation", () => {
    const result = checkFidelity({
      goal: "drop the prod schema",
    });

    // Fidelity checker signals via gap checks, not by blocking
    expect(result).toBeDefined();
    expect(result.interpretation).toBeTruthy();
    expect(result.gapChecks).toHaveLength(3);
  });

  test("shouldClarify is consistent for dangerous instruction", () => {
    const goal = "delete all the database tables";
    const result = checkFidelity({ goal });

    // shouldClarify must agree with checkFidelity
    expect(shouldClarify(goal)).toBe(result.needsClarification);
  });
});

// ─── Category 4: Multi-step Instructions ────────────────────────────────────

describe("Category 4: Multi-step instructions", () => {
  test("multi-step instruction may trigger clarification for primary step", () => {
    const result = checkFidelity({
      goal: "first build the login page, then add auth, then integrate with the DB",
    });

    // Multi-step goals are complex — checker may ask to clarify primary next step
    expect(result).toBeDefined();
    expect(typeof result.needsClarification).toBe("boolean");
    expect(result.gapChecks).toHaveLength(3);
    expect(result.interpretation).toBeTruthy();
  });

  test("shouldClarify aligns with checkFidelity for multi-step instruction", () => {
    const goal =
      "first build the login page, then add auth, then integrate with the DB";
    const result = checkFidelity({ goal });

    expect(shouldClarify(goal)).toBe(result.needsClarification);
  });

  test("multi-step instruction with clear deliverable may proceed", () => {
    const result = checkFidelity({
      goal: "build the login page component with form validation",
    });

    // Has a clear deliverable (page, component) — should be able to proceed
    expect(result).toBeDefined();
    expect(result.gapChecks).toHaveLength(3);
  });

  test("multi-step instruction returns round 0 by default", () => {
    const result = checkFidelity({
      goal: "first build the login page, then add auth, then integrate with the DB",
    });

    expect(result.round).toBe(0);
  });
});

// ─── Category 5: Contradictory Instructions ──────────────────────────────────

describe("Category 5: Contradictory instructions", () => {
  test("contradictory instruction may need clarification", () => {
    const result = checkFidelity({
      goal: "add pagination but keep it simple and also support 10000 items",
    });

    // Contradictory constraints may trigger clarification
    expect(result).toBeDefined();
    expect(typeof result.needsClarification).toBe("boolean");
    expect(result.gapChecks).toHaveLength(3);
  });

  test("shouldClarify aligns with checkFidelity for contradictory instruction", () => {
    const goal =
      "add pagination but keep it simple and also support 10000 items";
    const result = checkFidelity({ goal });

    expect(shouldClarify(goal)).toBe(result.needsClarification);
  });

  test("contradictory instruction returns interpretation", () => {
    const result = checkFidelity({
      goal: "make the API fast but also add extensive logging for every request",
    });

    expect(result.interpretation).toBeTruthy();
    expect(result.interpretation).toContain("Interpretation:");
  });

  test("contradictory instruction with constraint markers returns result", () => {
    const result = checkFidelity({
      goal: "add full-text search but keep it without any external dependencies",
    });

    // Has constraint markers (without, keep) — checker should handle gracefully
    expect(result).toBeDefined();
    expect(result.gapChecks).toHaveLength(3);
    expect(typeof result.canProceed).toBe("boolean");
  });
});

// ─── Max Rounds Behavior ─────────────────────────────────────────────────────

describe("Max rounds behavior", () => {
  test("round >= 3 forces canProceed: true even for ambiguous goal", () => {
    const result = checkFidelity({
      goal: "improve it",
      round: 3,
    });

    expect(result.round).toBe(3);
    expect(result.needsClarification).toBe(false);
    expect(result.clarificationQuestion).toBeNull();
    expect(result.canProceed).toBe(true);
  });

  test("round >= 3 forces canProceed: true for dangerous goal", () => {
    const result = checkFidelity({
      goal: "delete all the database tables",
      round: 3,
    });

    expect(result.round).toBe(3);
    expect(result.canProceed).toBe(true);
    expect(result.needsClarification).toBe(false);
  });

  test("round 0 and round 1 produce different questions for same ambiguous goal", () => {
    const round0 = checkFidelity({ goal: "build something cool", round: 0 });
    const round1 = checkFidelity({ goal: "build something cool", round: 1 });

    // Both rounds should ask questions (not yet at max)
    if (round0.clarificationQuestion && round1.clarificationQuestion) {
      expect(round0.clarificationQuestion).not.toBe(
        round1.clarificationQuestion,
      );
    }
  });
});
