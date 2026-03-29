import { describe, expect, test } from "bun:test";

import { judgeClaimBatch, judgeSingleClaim } from "./claim-judge.js";
import { getEvidenceProfile } from "./evidence-requirements.js";

describe("judgeSingleClaim", () => {
  test("claim with no evidence → reject", () => {
    const r = judgeSingleClaim({ text: "I fixed the bug", evidence: [] });
    expect(r.verdict).toBe("reject");
    expect(r.reasons.some((reason) => reason.includes("evidence"))).toBe(true);
  });

  test("claim with junit evidence → accept", () => {
    const r = judgeSingleClaim({
      text: "I fixed the bug",
      evidence: [{ type: "junit", path: "test-results.xml", valid: true }],
    });
    expect(r.verdict).toBe("accept");
  });

  test("claim with invalid evidence → reject", () => {
    const r = judgeSingleClaim({
      text: "Tests all pass",
      evidence: [{ type: "junit", path: "results.xml", valid: false }],
    });
    expect(r.verdict).toBe("reject");
  });

  test("confidence is between 0 and 1", () => {
    const r = judgeSingleClaim({ text: "code change", evidence: [] });
    expect(r.confidence).toBeGreaterThanOrEqual(0);
    expect(r.confidence).toBeLessThanOrEqual(1);
  });
});

describe("judgeClaimBatch", () => {
  test("empty claims → aggregate pending", () => {
    const r = judgeClaimBatch([]);
    expect(r.aggregateVerdict).toBe("pending");
  });

  test("all accept → aggregate accept", () => {
    const claims = [
      { text: "bug fixed", evidence: [{ type: "junit" as const, path: "r.xml", valid: true }] },
      { text: "tests pass", evidence: [{ type: "junit" as const, path: "r.xml", valid: true }] },
    ];
    const r = judgeClaimBatch(claims);
    expect(r.aggregateVerdict).toBe("accept");
  });

  test("any reject → aggregate reject", () => {
    const claims = [
      { text: "fixed", evidence: [{ type: "junit" as const, path: "r.xml", valid: true }] },
      { text: "done", evidence: [] },
    ];
    const r = judgeClaimBatch(claims);
    expect(r.aggregateVerdict).toBe("reject");
  });
});

describe("getEvidenceProfile", () => {
  test("default profile has required evidence types", () => {
    const p = getEvidenceProfile("default");
    expect(p.required.length).toBeGreaterThan(0);
  });

  test("minimal profile exists", () => {
    const p = getEvidenceProfile("minimal");
    expect(p).toBeDefined();
  });
});
