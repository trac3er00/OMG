import { describe, test, expect } from "bun:test";
import { runMetacognitivePipeline } from "./pipeline.js";
import { MetacognitiveReportSchema } from "./types.js";

describe("metacognitive/pipeline", () => {
  test("high confidence without high stakes → no verification", () => {
    const output = runMetacognitivePipeline({
      claim: "The code is correct",
      confidence: 0.95,
      evidence_refs: ["tests.json", "coverage.json"],
      task_complexity: 1,
    });
    expect(output.verification_performed).toBe(false);
    expect(output.token_cost_multiplier).toBe(1.0);
  });

  test("low confidence triggers verification", () => {
    const output = runMetacognitivePipeline({
      claim: "The implementation is complete",
      confidence: 0.4,
      evidence_refs: [],
      task_complexity: 2,
    });
    expect(output.verification_performed).toBe(true);
    expect(output.token_cost_multiplier).toBeGreaterThan(1.0);
  });

  test("high stakes task triggers verification", () => {
    const output = runMetacognitivePipeline({
      claim: "Deploy to production",
      confidence: 0.9,
      evidence_refs: ["proof.json"],
      domain: "deployment",
      is_high_stakes: true,
      task_complexity: 2,
    });
    expect(output.verification_performed).toBe(true);
  });

  test("token cost multiplier ≤ 3x baseline", () => {
    const output = runMetacognitivePipeline({
      claim: "Security audit complete",
      confidence: 0.3,
      evidence_refs: [],
      domain: "security",
      task_complexity: 4,
    });
    expect(output.token_cost_multiplier).toBeLessThanOrEqual(3.0);
  });

  test("report includes human-auditable evidence", () => {
    const output = runMetacognitivePipeline({
      claim: "Tests pass",
      confidence: 0.9,
      evidence_refs: ["junit.xml", "coverage.json"],
    });
    expect(output.report.human_auditable_evidence.length).toBeGreaterThan(0);
  });

  test("report validates against schema", () => {
    const output = runMetacognitivePipeline({
      claim: "Task complete",
      confidence: 0.8,
      evidence_refs: ["proof.json"],
    });
    expect(MetacognitiveReportSchema.safeParse(output.report).success).toBe(
      true,
    );
  });

  test("epistemic assessment matches confidence level", () => {
    const low = runMetacognitivePipeline({
      claim: "Test",
      confidence: 0.2,
      evidence_refs: [],
    });
    expect(low.epistemic_assessment.state.classification).toBe("unknown");

    const high = runMetacognitivePipeline({
      claim: "Test",
      confidence: 0.95,
      evidence_refs: ["proof.json"],
    });
    expect(high.epistemic_assessment.state.classification).toBe("known");
  });

  test("novel domain flags unknown_unknowns", () => {
    const output = runMetacognitivePipeline({
      claim: "Robotics safe",
      confidence: 0.9,
      evidence_refs: ["proof.json"],
      domain: "robotics",
    });
    expect(output.epistemic_assessment.novel_domain).toBe(true);
    expect(output.report.epistemic_state.unknown_unknowns_detected).toBe(true);
  });
});
