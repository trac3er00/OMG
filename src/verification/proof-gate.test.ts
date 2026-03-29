import { describe, test, expect } from "bun:test";
import { productionGate, evaluateProofGate } from "./proof-gate.js";
import { ProofChain } from "./proof-chain.js";

describe("productionGate", () => {
  test("empty evidence → blocked with missing primitives", () => {
    const r = productionGate({});
    expect(r.status).toBe("blocked");
    expect(r.blockers.length).toBeGreaterThan(0);
  });

  test("junit + coverage → pass", () => {
    const r = productionGate({
      junit: { tests: 10, failures: 0, errors: 0 },
      coverage: { line_rate: 0.85 },
    });
    expect(r.status).toBe("pass");
    expect(r.blockers).toHaveLength(0);
  });

  test("junit failures present → blocked", () => {
    const r = productionGate({
      junit: { tests: 10, failures: 2, errors: 0 },
      coverage: { line_rate: 0.85 },
    });
    expect(r.status).toBe("blocked");
    expect(r.blockers.some((b) => b.includes("fail"))).toBe(true);
  });

  test("coverage below threshold → blocked", () => {
    const r = productionGate({
      junit: { tests: 10, failures: 0, errors: 0 },
      coverage: { line_rate: 0.4 },
    });
    expect(r.status).toBe("blocked");
  });
});

describe("evaluateProofGate", () => {
  test("returns status field", () => {
    const r = evaluateProofGate({ evidence: {} });
    expect(["pass", "fail", "blocked", "pending"]).toContain(r.status);
  });

  test("complete evidence → pass verdict", () => {
    const r = evaluateProofGate({
      evidence: {
        junit: { tests: 5, failures: 0, errors: 0 },
        coverage: { line_rate: 0.9 },
      },
    });
    expect(r.status).toBe("pass");
  });
});

describe("ProofChain", () => {
  test("new chain starts empty", () => {
    const chain = new ProofChain("run-001");
    expect(chain.entries()).toHaveLength(0);
  });

  test("addEntry adds to chain", () => {
    const chain = new ProofChain("run-001");
    chain.addEntry({ step: "junit", status: "pass", evidenceType: "junit" });
    expect(chain.entries()).toHaveLength(1);
  });

  test("overall status pass when all pass", () => {
    const chain = new ProofChain("run-001");
    chain.addEntry({ step: "junit", status: "pass", evidenceType: "junit" });
    chain.addEntry({ step: "coverage", status: "pass", evidenceType: "coverage" });
    expect(chain.overallStatus()).toBe("pass");
  });

  test("overall status fail when any fails", () => {
    const chain = new ProofChain("run-001");
    chain.addEntry({ step: "junit", status: "pass", evidenceType: "junit" });
    chain.addEntry({ step: "coverage", status: "fail", evidenceType: "coverage" });
    expect(chain.overallStatus()).toBe("fail");
  });
});
