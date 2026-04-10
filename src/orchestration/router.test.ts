import { describe, expect, test } from "bun:test";

import { ModelTier, TeamRouter } from "./router.js";
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

describe("TeamRouter model tier dispatch", () => {
  test("simple signals route to haiku tier", async () => {
    let dispatchedTier: ModelTier | undefined;
    const router = TeamRouter.create({
      dispatchFn: async (_agentName, _prompt, _context, modelTier) => {
        dispatchedTier = modelTier;
        return { output: "ok", exitCode: 0 };
      },
    });

    const result = await router.route({
      target: "auto",
      problem: "review tiny typo fix",
      context: "",
      routingSignals: { files: 1, loc: 10, deps: 0, errors: 0 },
    });

    expect(result.evidence.model_tier).toBe(ModelTier.Haiku);
    expect(dispatchedTier).toBe(ModelTier.Haiku);
  });

  test("standard signals route to sonnet tier", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "implement a moderate backend feature",
      context: "",
      routingSignals: { files: 2, loc: 250, deps: 3, errors: 1 },
    });

    expect(result.evidence.model_tier).toBe(ModelTier.Sonnet);
    expect(result.evidence.base_model_tier).toBe(ModelTier.Sonnet);
  });

  test("complex signals route to opus tier", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "orchestrate a large multi-package refactor",
      context: "",
      routingSignals: { files: 12, loc: 1_500, deps: 12, errors: 6 },
    });

    expect(result.evidence.model_tier).toBe(ModelTier.Opus);
    expect(result.evidence.base_model_tier).toBe(ModelTier.Opus);
  });

  test("budget pressure downgrades to a cheaper tier", async () => {
    const router = TeamRouter.create();
    const result = await router.route({
      target: "auto",
      problem: "orchestrate a large multi-package refactor",
      context: "",
      routingSignals: { files: 12, loc: 1_500, deps: 12, errors: 6 },
      budget: {
        runId: "task-20",
        cpuSecondsLimit: 0,
        memoryMbLimit: 0,
        wallTimeSecondsLimit: 0,
        tokenLimit: 100,
        networkBytesLimit: 0,
        cpuSecondsUsed: 0,
        memoryMbPeak: 0,
        wallTimeSecondsUsed: 0,
        tokensUsed: 85,
        networkBytesUsed: 0,
        exceeded: false,
        exceededDimensions: [],
      },
    });

    expect(result.evidence.base_model_tier).toBe(ModelTier.Opus);
    expect(result.evidence.model_tier).toBe(ModelTier.Sonnet);
    expect(result.evidence.model_tier_budget_downgraded).toBe(true);
    expect(result.evidence.budget_remaining_ratio).toBe(0.15);
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
    const evaluation = critic.evaluate("verified the patch", [
      ".sisyphus/evidence/task-33-router.txt",
    ]);

    expect(evaluation.verdict).toBe("accept");
  });
});
