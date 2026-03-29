import { describe, expect, test } from "bun:test";

import { SelfImprovingRouter } from "./self-improving.js";

describe("SelfImprovingRouter", () => {
  test("prefers the agent with the strongest success rate for a task type", () => {
    const router = SelfImprovingRouter.create({
      agents: ["agent-a", "agent-b"],
    });

    for (let index = 0; index < 10; index += 1) {
      router.recordOutcome("agent-a", "task-x", true);
      router.recordOutcome("agent-b", "task-x", false);
    }

    const optimization = router.optimize("task-x");

    expect(router.route("task-x")).toBe("agent-a");
    expect(optimization.recommendedAgent).toBe("agent-a");
    expect(optimization.weights["agent-a"]).toBeGreaterThan(optimization.weights["agent-b"]);
    expect(optimization.rankings[0]?.successRate).toBe(1);
    expect(optimization.rankings[1]?.successRate).toBe(0);
  });

  test("tracks routing performance independently per task type", () => {
    const router = SelfImprovingRouter.create({
      agents: ["agent-a", "agent-b"],
    });

    for (let index = 0; index < 5; index += 1) {
      router.recordOutcome("agent-a", "backend", true);
      router.recordOutcome("agent-b", "research", true);
    }
    for (let index = 0; index < 5; index += 1) {
      router.recordOutcome("agent-a", "research", false);
      router.recordOutcome("agent-b", "backend", false);
    }

    expect(router.route("backend")).toBe("agent-a");
    expect(router.route("research")).toBe("agent-b");
  });

  test("falls back to the seeded order when no performance data exists", () => {
    const router = SelfImprovingRouter.create({
      agents: ["agent-a", "agent-b"],
    });

    expect(router.route("unknown-task")).toBe("agent-a");
  });
});
