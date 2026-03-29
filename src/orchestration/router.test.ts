import { describe, expect, test } from "bun:test";

import { TeamRouter } from "./router.js";
import { SkepticCritic } from "./router-critics.js";

describe("TeamRouter target selection", () => {
  test("auto routes code signal to codex", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "build a React component",
      context: "",
    });

    expect(result.status).toBe("ok");
    expect(result.evidence.selected_target).toBe("codex");
  });

  test("auto routes infra signal to codex", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "deploy to kubernetes",
      context: "",
    });

    expect(result.status).toBe("ok");
    expect(result.evidence.selected_target).toBe("codex");
  });

  test("auto routes research signal to gemini", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "research the tradeoffs between two caching strategies",
      context: "",
    });

    expect(result.status).toBe("ok");
    expect(result.evidence.selected_target).toBe("gemini");
  });
});

describe("TeamRouter execution mode", () => {
  test("ccg executes workers in parallel", async () => {
    const router = TeamRouter.create({
      dispatchFn: async (agentName) => {
        const delayMs = agentName === "codex" ? 35 : 35;
        await Bun.sleep(delayMs);
        return { output: `${agentName}:ok`, exitCode: 0 };
      },
    });

    const startedAt = Date.now();
    const result = await router.route({
      target: "ccg",
      problem: "review frontend and backend",
      context: "",
    });
    const elapsedMs = Date.now() - startedAt;

    expect(result.status).toBe("ok");
    expect(result.evidence.parallel_execution).toBe(true);
    expect((result.evidence.execution as readonly unknown[]).length).toBe(2);
    expect(elapsedMs).toBeLessThan(65);
  });
});

describe("SkepticCritic", () => {
  test("flags claims without evidence as warn", () => {
    const critic = new SkepticCritic();
    const evaluation = critic.evaluate("implemented a full fix", []);

    expect(evaluation.verdict).toBe("warn");
    expect(evaluation.reason.toLowerCase()).toContain("evidence");
  });

  test("accepts evidence-backed claims", () => {
    const critic = new SkepticCritic();
    const evaluation = critic.evaluate("verified the patch", [".sisyphus/evidence/task-33-router.txt"]);

    expect(evaluation.verdict).toBe("accept");
  });
});
