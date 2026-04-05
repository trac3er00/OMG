import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import {
  RELIABILITY_VERSION,
  measureSameInputConsistency,
  measureCrossRunConsistency,
  measureIntraRunStability,
  measureErrorSeverityBounding,
  measureSafeFailureModes,
  aggregateSnapshot,
  persistSnapshot,
  ReliabilitySnapshotSchema,
} from "./metrics.js";

const TEST_DIR = "/tmp/omg-reliability-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(TEST_DIR, { recursive: true });
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("reliability/metrics", () => {
  test("RELIABILITY_VERSION is 1.0.0", () => {
    expect(RELIABILITY_VERSION).toBe("1.0.0");
  });

  describe("measureSameInputConsistency", () => {
    test("identical outputs score 1.0", () => {
      const result = measureSameInputConsistency([
        "output-A",
        "output-A",
        "output-A",
      ]);
      expect(result.score).toBe(1.0);
      expect(result.status).toBe("pass");
    });

    test("all different outputs scores near 0", () => {
      const result = measureSameInputConsistency(["A", "B", "C", "D", "E"]);
      expect(result.score).toBeLessThan(0.3);
    });

    test("empty outputs returns unknown status", () => {
      const result = measureSameInputConsistency([]);
      expect(result.status).toBe("unknown");
    });

    test("single output scores 1.0", () => {
      const result = measureSameInputConsistency(["only-one"]);
      expect(result.score).toBe(1.0);
    });

    test("sample_count reflects input size", () => {
      const result = measureSameInputConsistency(["A", "A", "B"]);
      expect(result.sample_count).toBe(3);
    });
  });

  describe("measureCrossRunConsistency", () => {
    test("all same scores → consistency 1.0", () => {
      const result = measureCrossRunConsistency([0.8, 0.8, 0.8, 0.8]);
      expect(result.score).toBeCloseTo(1.0, 2);
    });

    test("high variance → low consistency", () => {
      const result = measureCrossRunConsistency([0.1, 0.9, 0.1, 0.9]);
      expect(result.score).toBeLessThan(0.7);
    });

    test("empty array returns unknown", () => {
      const result = measureCrossRunConsistency([]);
      expect(result.status).toBe("unknown");
    });

    test("score is 0-1", () => {
      const result = measureCrossRunConsistency([0.3, 0.5, 0.7, 0.4, 0.6]);
      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.score).toBeLessThanOrEqual(1);
    });
  });

  describe("measureIntraRunStability", () => {
    test("stable sequence (no transitions) scores 1.0", () => {
      const result = measureIntraRunStability(["A", "A", "A", "A"]);
      expect(result.score).toBe(1.0);
    });

    test("alternating outputs scores 0", () => {
      const result = measureIntraRunStability(["A", "B", "A", "B"]);
      expect(result.score).toBe(0);
    });

    test("single output scores 1.0", () => {
      const result = measureIntraRunStability(["A"]);
      expect(result.score).toBe(1.0);
    });
  });

  describe("measureErrorSeverityBounding", () => {
    test("no errors exceeding max scores 1.0", () => {
      const result = measureErrorSeverityBounding([0.1, 0.3, 0.5, 0.6]);
      expect(result.score).toBe(1.0);
      expect(result.status).toBe("pass");
    });

    test("all errors exceed max scores 0", () => {
      const result = measureErrorSeverityBounding([0.9, 0.95, 0.99], 0.8);
      expect(result.score).toBe(0);
      expect(result.status).toBe("fail");
    });

    test("empty errors scores 1.0", () => {
      const result = measureErrorSeverityBounding([]);
      expect(result.score).toBe(1.0);
    });
  });

  describe("measureSafeFailureModes", () => {
    test("all safe failures scores 1.0", () => {
      const result = measureSafeFailureModes(["safe", "safe", "safe"]);
      expect(result.score).toBe(1.0);
    });

    test("all unsafe failures scores 0", () => {
      const result = measureSafeFailureModes(["unsafe", "unsafe"]);
      expect(result.score).toBe(0);
    });

    test("mixed safe/unsafe scores proportionally", () => {
      const result = measureSafeFailureModes([
        "safe",
        "safe",
        "unsafe",
        "safe",
      ]);
      expect(result.score).toBeCloseTo(0.75, 5);
    });

    test("empty outcomes scores 1.0", () => {
      const result = measureSafeFailureModes([]);
      expect(result.score).toBe(1.0);
    });
  });

  describe("aggregateSnapshot", () => {
    test("all passing metrics → overall pass", () => {
      const metrics = [
        measureSameInputConsistency(["A", "A", "A"]),
        measureSafeFailureModes(["safe", "safe"]),
      ];
      const snapshot = aggregateSnapshot("test-agent", "code-review", metrics);
      expect(snapshot.overall_status).toBe("pass");
      expect(snapshot.schema_version).toBe(RELIABILITY_VERSION);
    });

    test("any failing metric → overall fail", () => {
      const metrics = [measureSameInputConsistency(["A", "B", "C"])];
      const snapshot = aggregateSnapshot("test-agent", "code-review", metrics);
      expect(snapshot.overall_status).toBe("fail");
    });

    test("overall_score is average of valid metric scores", () => {
      const m1 = measureSameInputConsistency(["A", "A", "A"]);
      const m2 = measureSafeFailureModes(["safe", "safe"]);
      const snapshot = aggregateSnapshot("agent", "task", [m1, m2]);
      expect(snapshot.overall_score).toBeGreaterThan(0);
      expect(snapshot.overall_score).toBeLessThanOrEqual(1);
    });

    test("snapshot validates against schema", () => {
      const metrics = [measureSameInputConsistency(["A", "A"])];
      const snapshot = aggregateSnapshot("agent", "task", metrics);
      expect(ReliabilitySnapshotSchema.safeParse(snapshot).success).toBe(true);
    });
  });

  describe("persistSnapshot", () => {
    test("creates history.jsonl file", () => {
      const metrics = [measureSameInputConsistency(["A", "A"])];
      const snapshot = aggregateSnapshot("agent", "task", metrics);
      persistSnapshot(snapshot, TEST_DIR);
      const historyPath = join(
        TEST_DIR,
        ".omg",
        "reliability",
        "history.jsonl",
      );
      expect(existsSync(historyPath)).toBe(true);
    });

    test("history is append-only (multiple snapshots)", () => {
      const metrics = [measureSameInputConsistency(["A", "A"])];
      const s1 = aggregateSnapshot("agent", "task", metrics);
      const s2 = aggregateSnapshot("agent", "task", metrics);
      persistSnapshot(s1, TEST_DIR);
      persistSnapshot(s2, TEST_DIR);
      const historyPath = join(
        TEST_DIR,
        ".omg",
        "reliability",
        "history.jsonl",
      );
      const lines = readFileSync(historyPath, "utf8").trim().split("\n");
      expect(lines.length).toBe(2);
    });

    test("each history line is valid JSON", () => {
      const metrics = [measureSafeFailureModes(["safe"])];
      const snapshot = aggregateSnapshot("agent", "task", metrics);
      persistSnapshot(snapshot, TEST_DIR);
      const historyPath = join(
        TEST_DIR,
        ".omg",
        "reliability",
        "history.jsonl",
      );
      const lines = readFileSync(historyPath, "utf8").trim().split("\n");
      for (const line of lines) {
        expect(() => JSON.parse(line)).not.toThrow();
      }
    });
  });
});
