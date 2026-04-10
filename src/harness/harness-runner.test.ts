import { describe, test, expect } from "bun:test";
import {
  HARNESS_VERSION,
  HarnessRunner,
  createPassingRunner,
  createFailingRunner,
  HarnessReportSchema,
  LayerResultSchema,
} from "./harness-runner.js";

describe("harness/harness-runner", () => {
  test("HARNESS_VERSION is 1.0.0", () => {
    expect(HARNESS_VERSION).toBe("1.0.0");
  });

  describe("LayerResult schema", () => {
    test("valid layer result passes", () => {
      expect(
        LayerResultSchema.safeParse({
          layer: 1,
          target: "src/context/",
          status: "pass",
          total: 20,
          passed: 20,
          failed: 0,
          duration_ms: 100,
        }).success,
      ).toBe(true);
    });

    test("layer below 1 fails", () => {
      expect(
        LayerResultSchema.safeParse({
          layer: 0,
          target: "src/",
          status: "pass",
          total: 10,
          passed: 10,
          failed: 0,
          duration_ms: 50,
        }).success,
      ).toBe(false);
    });

    test("layer above 5 fails", () => {
      expect(
        LayerResultSchema.safeParse({
          layer: 6,
          target: "src/",
          status: "pass",
          total: 10,
          passed: 10,
          failed: 0,
          duration_ms: 50,
        }).success,
      ).toBe(false);
    });
  });

  describe("HarnessRunner", () => {
    test("runs 3 layers sequentially", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));
      runner.register(createPassingRunner(2, "integration"));
      runner.register(createPassingRunner(3, "e2e"));

      const report = await runner.run({
        module: "src/context/",
        layers: [1, 2, 3],
      });
      expect(report.layers_executed).toEqual([1, 2, 3]);
      expect(report.layer_results.length).toBe(3);
      expect(typeof report.orchestration.phases.started_at).toBe("string");
      expect(typeof report.orchestration.phases.executed_at).toBe("string");
      expect(typeof report.orchestration.phases.verified_at).toBe("string");
      expect(typeof report.orchestration.phases.reported_at).toBe("string");
    });

    test("all-passing run returns overall_status pass", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));
      runner.register(createPassingRunner(2, "integration"));

      const report = await runner.run({ module: "src/test/", layers: [1, 2] });
      expect(report.overall_status).toBe("pass");
    });

    test("failure in any layer returns overall_status fail", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));
      runner.register(createFailingRunner(2, "integration"));

      const report = await runner.run({ module: "src/test/", layers: [1, 2] });
      expect(report.overall_status).toBe("fail");
      expect(
        report.orchestration.reliability.snapshot.overall_score,
      ).toBeLessThan(1);
    });

    test("missing runner produces skip result", async () => {
      const runner = new HarnessRunner();
      const report = await runner.run({ module: "src/test/", layers: [1] });
      expect(report.layer_results[0]?.status).toBe("skip");
    });

    test("report aggregates total test counts", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit", 15));
      runner.register(createPassingRunner(2, "integration", 8));

      const report = await runner.run({ module: "src/test/", layers: [1, 2] });
      expect(report.total_tests).toBe(23);
      expect(report.passed_tests).toBe(23);
      expect(report.failed_tests).toBe(0);
    });

    test("report has schema_version field", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));
      const report = await runner.run({ module: "src/test/" });
      expect(report.schema_version).toBe(HARNESS_VERSION);
      expect(HarnessReportSchema.safeParse(report).success).toBe(true);
    });

    test("default layers are 1,2,3 when not specified", async () => {
      const runner = new HarnessRunner();
      const report = await runner.run({ module: "src/test/" });
      expect(report.layers_executed).toEqual([1, 2, 3]);
    });

    test("run_id is present in report", async () => {
      const runner = new HarnessRunner();
      const report = await runner.run({
        module: "src/test/",
        runId: "test-run-001",
      });
      expect(report.run_id).toBe("test-run-001");
    });

    test("failure count reflected in passed_tests", async () => {
      const runner = new HarnessRunner();
      runner.register(createFailingRunner(1, "unit", 3));
      const report = await runner.run({ module: "src/test/", layers: [1] });
      expect(report.failed_tests).toBe(3);
      expect(report.passed_tests).toBe(7);
    });

    test("high-complexity run orchestrates debate → governance → reliability", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "start"));
      runner.register(createPassingRunner(2, "execute"));
      runner.register(createPassingRunner(3, "verify"));

      const report = await runner.run({
        module: "src/harness/",
        layers: [1, 2, 3],
        complexity: 8,
        context:
          "Validate harness orchestration against validated debate chain",
        governance: {
          signedApproval: true,
          attested: true,
        },
      });

      expect(report.orchestration.debate.invoked).toBe(true);
      expect(report.orchestration.governance.allowed).toBe(true);
      expect(report.orchestration.governance.action).toBe("allow");
      expect(report.orchestration.reliability.snapshot.overall_score).toBe(1);
      expect(report.orchestration.reliability.gate.passed).toBe(true);
      expect(report.overall_status).toBe("pass");
    });

    test("governance gate blocks execution without approval", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));

      const report = await runner.run({
        module: "src/harness/",
        layers: [1],
        complexity: 8,
        governance: {
          signedApproval: false,
          attested: true,
        },
      });

      expect(report.orchestration.governance.allowed).toBe(false);
      expect(report.orchestration.governance.action).toBe("deny");
      expect(report.layer_results[0]?.status).toBe("error");
      expect(report.overall_status).toBe("fail");
    });
  });

  describe("report compatibility with evidence schema", () => {
    test("report can be used as evidence artifact base", async () => {
      const runner = new HarnessRunner();
      runner.register(createPassingRunner(1, "unit"));
      const report = await runner.run({ module: "src/test/" });
      expect(typeof report.schema_version).toBe("string");
      expect(typeof report.run_id).toBe("string");
    });
  });
});
