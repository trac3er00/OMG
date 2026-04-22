import { describe, test, expect } from "bun:test";
import { sanitizeContent } from "../../../src/security/content-sanitizer.js";
import { validateClaim } from "../../../src/governance/evidence-enforcer.js";
import { understandIntent } from "../../../src/intent/index.js";

describe("stress tests", () => {
  test("sanitizeContent handles 10000 rapid calls", () => {
    const input = "Hello \u202Ainjection\u202E World";
    for (let i = 0; i < 10000; i++) {
      const result = sanitizeContent(input);
      expect(result.sanitized).not.toContain("\u202A");
    }
  });

  test("validateClaim handles concurrent validation", () => {
    const claims = Array.from({ length: 100 }, (_, i) => ({
      type: "completion" as const,
      evidence: { testOutput: `PASS-${i}`, files: [`file-${i}.ts`] },
    }));
    const results = claims.map((c) => validateClaim(c));
    expect(results.every((r) => r.valid)).toBe(true);
  });

  test("understandIntent handles 1000 calls", () => {
    const prompts = ["fix typo", "add feature", "redesign architecture"];
    for (let i = 0; i < 1000; i++) {
      const result = understandIntent(prompts[i % 3]);
      expect(typeof result.intent).toBe("string");
      expect(typeof result.complexity.riskLevel).toBe("string");
    }
  });
});
