import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import {
  TAXONOMY_VERSION,
  classifyFailure,
  persistFailureReport,
  summarizeTaxonomy,
  FailureReportSchema,
} from "./failure-taxonomy.js";

const TEST_DIR = "/tmp/omg-taxonomy-test";
beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(TEST_DIR, { recursive: true });
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("harness/failure-taxonomy", () => {
  test("TAXONOMY_VERSION is 1.0.0", () => {
    expect(TAXONOMY_VERSION).toBe("1.0.0");
  });

  describe("classifyFailure", () => {
    test("context loss → context-related", () => {
      const report = classifyFailure({
        error_message: "context.json expired and was lost",
      });
      expect(report.category).toBe("context-related");
    });

    test("timeout → tool-related", () => {
      const report = classifyFailure({
        error_message: "timeout:task-1:30000ms",
      });
      expect(report.category).toBe("tool-related");
    });

    test("module not found → hallucination-related", () => {
      const report = classifyFailure({
        error_message: "module './nonexistent' was not found",
      });
      expect(report.category).toBe("hallucination-related");
    });

    test("assertion failure → reasoning-related", () => {
      const report = classifyFailure({
        error_message: "assertion failed: expected 42 received 0",
      });
      expect(report.category).toBe("reasoning-related");
    });

    test("unrecognized error → unknown", () => {
      const report = classifyFailure({
        error_message: "something completely unrelated happened",
      });
      expect(report.category).toBe("unknown");
    });

    test("circuit open → tool-related", () => {
      const report = classifyFailure({ error_message: "circuit_open:task-id" });
      expect(report.category).toBe("tool-related");
    });

    test("ENOENT → tool-related", () => {
      const report = classifyFailure({
        error_message: "ENOENT: no such file or directory",
      });
      expect(report.category).toBe("tool-related");
    });

    test("approval required → governance-related", () => {
      const report = classifyFailure({
        error_message: "signed approval required before execute",
      });
      expect(report.category).toBe("governance-related");
    });

    test("reliability threshold breach → reliability-related", () => {
      const report = classifyFailure({
        error_message:
          "reliability score below threshold after calibration drift",
      });
      expect(report.category).toBe("reliability-related");
    });

    test("report validates against schema", () => {
      const report = classifyFailure({ error_message: "timeout:task:5000ms" });
      expect(FailureReportSchema.safeParse(report).success).toBe(true);
    });

    test("custom failure_id is used", () => {
      const report = classifyFailure({
        error_message: "error",
        failure_id: "custom-001",
      });
      expect(report.failure_id).toBe("custom-001");
    });

    test("confidence is 0-1", () => {
      const report = classifyFailure({ error_message: "context lost" });
      expect(report.confidence).toBeGreaterThanOrEqual(0);
      expect(report.confidence).toBeLessThanOrEqual(1);
    });
  });

  describe("persistFailureReport", () => {
    test("creates failures.jsonl", () => {
      const report = classifyFailure({ error_message: "timeout:t:5000ms" });
      persistFailureReport(report, TEST_DIR);
      expect(
        existsSync(join(TEST_DIR, ".omg", "harness", "failures.jsonl")),
      ).toBe(true);
    });

    test("multiple reports are appended", () => {
      const r1 = classifyFailure({ error_message: "timeout:t:5000ms" });
      const r2 = classifyFailure({ error_message: "ENOENT file" });
      persistFailureReport(r1, TEST_DIR);
      persistFailureReport(r2, TEST_DIR);
      const lines = readFileSync(
        join(TEST_DIR, ".omg", "harness", "failures.jsonl"),
        "utf8",
      )
        .trim()
        .split("\n");
      expect(lines.length).toBe(2);
    });
  });

  describe("summarizeTaxonomy", () => {
    test("counts per category", () => {
      const reports = [
        classifyFailure({ error_message: "context expired" }),
        classifyFailure({ error_message: "context lost" }),
        classifyFailure({ error_message: "timeout:task:100ms" }),
      ];
      const summary = summarizeTaxonomy(reports);
      expect(summary["context-related"]).toBe(2);
      expect(summary["tool-related"]).toBe(1);
    });

    test("all categories present in summary", () => {
      const summary = summarizeTaxonomy([]);
      const categories = [
        "context-related",
        "tool-related",
        "governance-related",
        "reliability-related",
        "reasoning-related",
        "hallucination-related",
        "unknown",
      ];
      for (const cat of categories) {
        expect(cat in summary).toBe(true);
      }
    });
  });
});
