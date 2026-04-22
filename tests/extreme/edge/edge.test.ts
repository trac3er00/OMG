import { describe, test, expect } from "bun:test";
import { sanitizeContent } from "../../../src/security/content-sanitizer.js";
import {
  scoreTrustChange,
  getTrustDecision,
} from "../../../src/security/trust-review.js";
import { validateClaim } from "../../../src/governance/evidence-enforcer.js";

describe("edge cases", () => {
  test("sanitizeContent handles empty string", () => {
    expect(sanitizeContent("").sanitized).toBe("");
  });

  test("sanitizeContent handles null-like input", () => {
    expect(() => sanitizeContent(null as unknown as string)).not.toThrow();
  });

  test("sanitizeContent handles very long string", () => {
    const long = "a".repeat(100000);
    expect(() => sanitizeContent(long)).not.toThrow();
  });

  test("scoreTrustChange handles zero-count event", () => {
    const result = scoreTrustChange({ type: "mcp_server_added", count: 0 });
    expect(result).toBe(0);
  });

  test("getTrustDecision returns deny for high score", () => {
    expect(getTrustDecision(100)).toBe("deny");
  });

  test("getTrustDecision returns allow for low score", () => {
    expect(getTrustDecision(10)).toBe("allow");
  });

  test("validateClaim handles undefined evidence gracefully", () => {
    const result = validateClaim({ type: "completion", evidence: undefined });
    expect(result.valid).toBe(false);
  });
});
