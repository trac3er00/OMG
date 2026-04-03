import { describe, test, expect } from "bun:test";
import {
  REPRODUCIBILITY_RUNS,
  ReproducibilityResultSchema,
  BehavioralDiffResultSchema,
  measureReproducibility,
  computeBehavioralDiff,
} from "./reproducibility.js";

describe("harness/reproducibility", () => {
  test("REPRODUCIBILITY_RUNS is 10", () => {
    expect(REPRODUCIBILITY_RUNS).toBe(10);
  });

  describe("measureReproducibility", () => {
    test("identical outputs → score 1.0, deterministic", () => {
      const result = measureReproducibility([
        "output-A",
        "output-A",
        "output-A",
        "output-A",
      ]);
      expect(result.score).toBe(1.0);
      expect(result.is_deterministic).toBe(true);
      expect(result.status).toBe("pass");
    });

    test("all different outputs → low score, non-deterministic", () => {
      const result = measureReproducibility(["A", "B", "C", "D", "E"]);
      expect(result.score).toBeLessThan(0.3);
      expect(result.is_deterministic).toBe(false);
      expect(result.status).toBe("fail");
    });

    test("empty inputs → skip status", () => {
      const result = measureReproducibility([]);
      expect(result.status).toBe("skip");
      expect(result.runs).toBe(0);
    });

    test("single output → score 1.0", () => {
      const result = measureReproducibility(["only-one"]);
      expect(result.score).toBe(1.0);
    });

    test("result has layer 4", () => {
      const result = measureReproducibility(["A", "A"]);
      expect(result.layer).toBe(4);
    });

    test("sample_outputs limited to 3", () => {
      const result = measureReproducibility(["A", "A", "A", "A", "A"]);
      expect(result.sample_outputs.length).toBeLessThanOrEqual(3);
    });

    test("result validates against schema", () => {
      const result = measureReproducibility(["x", "x", "x"]);
      expect(ReproducibilityResultSchema.safeParse(result).success).toBe(true);
    });
  });

  describe("computeBehavioralDiff", () => {
    test("identical baselines → similarity 1.0", () => {
      const baseline = { accuracy: "0.95", latency: "50ms" };
      const result = computeBehavioralDiff(
        baseline,
        { ...baseline },
        "src/test/",
        "v1",
        "v2",
      );
      expect(result.similarity_score).toBe(1.0);
      expect(result.changes).toEqual([]);
      expect(result.additions).toEqual([]);
      expect(result.removals).toEqual([]);
      expect(result.status).toBe("pass");
    });

    test("detects additions", () => {
      const baseline = { a: "1" };
      const current = { a: "1", b: "2" };
      const result = computeBehavioralDiff(baseline, current, "mod");
      expect(result.additions).toContain("b");
    });

    test("detects removals", () => {
      const baseline = { a: "1", b: "2" };
      const current = { a: "1" };
      const result = computeBehavioralDiff(baseline, current, "mod");
      expect(result.removals).toContain("b");
    });

    test("detects changed values", () => {
      const baseline = { accuracy: "0.95" };
      const current = { accuracy: "0.80" };
      const result = computeBehavioralDiff(baseline, current, "mod");
      expect(result.changes.length).toBe(1);
      expect(result.changes[0]?.field).toBe("accuracy");
      expect(result.changes[0]?.from).toBe("0.95");
      expect(result.changes[0]?.to).toBe("0.80");
    });

    test("many changes → low similarity, fail status", () => {
      const baseline = { a: "1", b: "2", c: "3", d: "4" };
      const current = { a: "X", b: "Y", e: "Z" };
      const result = computeBehavioralDiff(baseline, current, "mod");
      expect(result.similarity_score).toBeLessThan(0.8);
      expect(result.status).toBe("fail");
    });

    test("result validates against schema", () => {
      const result = computeBehavioralDiff({ a: "1" }, { a: "1" }, "mod");
      expect(BehavioralDiffResultSchema.safeParse(result).success).toBe(true);
    });

    test("result has layer 5", () => {
      const result = computeBehavioralDiff({}, {}, "mod");
      expect(result.layer).toBe(5);
    });

    test("empty baseline and current → similarity 1.0", () => {
      const result = computeBehavioralDiff({}, {}, "mod");
      expect(result.similarity_score).toBe(1.0);
    });
  });
});
