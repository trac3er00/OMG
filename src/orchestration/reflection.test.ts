import { describe, expect, test } from "bun:test";

import { ReflectionEngine, type ReflectionPlanStep } from "./reflection.js";

interface ReflectionState {
  counter: number;
  completed: string[];
  status: string;
}

describe("ReflectionEngine rollback", () => {
  test("restores checkpoint after a failed step", async () => {
    const initialState: ReflectionState = {
      counter: 1,
      completed: ["checkpointed"],
      status: "ready",
    };
    const engine = ReflectionEngine.create({ initialState });

    const checkpointId = engine.createCheckpoint(engine.getState());
    const execution = await engine.executeStep(async (state) => {
      state.counter = 2;
      state.completed.push("failed-step");
      state.status = "failed";
      throw new Error("forced failure");
    });

    expect(execution.status).toBe("failed");
    expect(engine.getState()).toEqual({
      counter: 2,
      completed: ["checkpointed", "failed-step"],
      status: "failed",
    });

    const rollback = engine.rollback(checkpointId);
    expect(rollback.state).toEqual(initialState);
    expect(engine.getState()).toEqual(initialState);
  });
});

describe("ReflectionEngine planning", () => {
  test("automatically rolls back to the last checkpoint when a plan step fails", async () => {
    const engine = ReflectionEngine.create<ReflectionState>({
      initialState: {
        counter: 0,
        completed: [],
        status: "ready",
      },
    });

    const steps: readonly ReflectionPlanStep<ReflectionState>[] = [
      {
        id: "step-1",
        description: "complete first step",
        run: async (state) => {
          state.counter += 1;
          state.completed.push("step-1");
          state.status = "step-1-complete";
          return state;
        },
      },
      {
        id: "step-2",
        description: "fail second step",
        run: async (state) => {
          state.counter += 1;
          state.completed.push("step-2");
          state.status = "step-2-failed";
          throw new Error("step-2 exploded");
        },
      },
    ];

    const result = await engine.runPlan("deliver orchestration plan", steps);

    expect(result.status).toBe("rolled_back");
    expect(result.completedSteps).toEqual(["step-1"]);
    expect(result.failedStepId).toBe("step-2");
    expect(result.state).toEqual({
      counter: 1,
      completed: ["step-1"],
      status: "step-1-complete",
    });
    expect(result.evaluation.verdict).toBe("fail");
    expect(result.evaluation.summary.toLowerCase()).toContain("restored");
    expect(engine.getState()).toEqual({
      counter: 1,
      completed: ["step-1"],
      status: "step-1-complete",
    });
  });

  test("stores a passing self-evaluation after successful completion", async () => {
    const engine = ReflectionEngine.create<ReflectionState>({
      initialState: {
        counter: 0,
        completed: [],
        status: "ready",
      },
    });

    const result = await engine.runPlan("close the loop", [
      {
        id: "reflect",
        description: "reflect on the task",
        run: (state) => {
          state.completed.push("reflect");
          state.status = "done";
          return state;
        },
      },
    ]);

    expect(result.status).toBe("completed");
    expect(result.evaluation.verdict).toBe("pass");
    expect(engine.getLastEvaluation()).toEqual(result.evaluation);
  });
});
