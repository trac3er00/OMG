import { describe, test, expect } from "bun:test";
import { validateClaim } from "./evidence-enforcer.js";

describe("validateClaim", () => {
  test("rejects claim with null evidence", () => {
    const result = validateClaim({ type: "completion", evidence: null });
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("evidence required");
  });

  test("rejects claim with empty evidence", () => {
    const result = validateClaim({ type: "completion", evidence: {} });
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("evidence required");
  });

  test("accepts claim with complete evidence", () => {
    const result = validateClaim({
      type: "completion",
      evidence: { testOutput: "PASS", files: ["src/test.ts"] },
    });
    expect(result.valid).toBe(true);
  });

  test("rejects completion claim missing required fields", () => {
    const result = validateClaim({
      type: "completion",
      evidence: { testOutput: "PASS" },
    });
    expect(result.valid).toBe(false);
    expect(result.reason).toContain("evidence required");
  });

  test("accepts unknown claim type with any evidence", () => {
    const result = validateClaim({
      type: "custom_type",
      evidence: { someData: true },
    });
    expect(result.valid).toBe(true);
  });
});
