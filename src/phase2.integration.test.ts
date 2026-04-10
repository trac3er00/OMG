import { expect, test } from "bun:test";
import { optimizeWaves, type WaveOptimizationResult } from "./planning/wave-optimizer";
import { getEscalationResult, type EscalationResult } from "./orchestration/escalation";
import { FilePlanningContextStore, type PlanningContext } from "./planning/context-retention";
import { extractTaskReference } from "./tracebank/traceability";

test("wave-optimizer export works", () => {
  const result: WaveOptimizationResult = optimizeWaves([
    { id: "task-1", description: "Plan phase 2", dependsOn: [] },
  ]);

  expect(result.totalTasks).toBe(1);
  expect(result.waves).toHaveLength(1);
});

test("escalation export works", () => {
  const result: EscalationResult = getEscalationResult({
    description: "Design a complex cross-model migration",
  });

  expect(result.model).toBeDefined();
  expect(typeof result.escalated).toBe("boolean");
});

test("context-retention export works", async () => {
  const store = new FilePlanningContextStore();
  const context: PlanningContext = {
    planId: "phase-2",
    topic: "Integration test coverage",
    interviewDecisions: { owner: "team" },
    researchFindings: ["ok"],
    createdAt: new Date().toISOString(),
    version: "2.7.0",
  };

  expect(store).toBeInstanceOf(FilePlanningContextStore);
  expect(typeof store.save).toBe("function");
  expect(context.planId).toBe("phase-2");
});

test("traceability export works", () => {
  expect(extractTaskReference("feat(T24): add phase 2 checks")).toBe("T24");
});
