import { afterEach, describe, expect, test } from "bun:test";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GovernanceCheckResult, ToolFabricResult } from "../../src/governance/tool-fabric.js";
import { ToolFabric } from "../../src/governance/tool-fabric.js";
import { understandIntent } from "../../src/intent/index.js";
import {
  resolveDecisionPoint,
  type OptionEntry,
  type Options131,
} from "../../src/intent/options.js";
import type { TeamDispatchRequest, TeamDispatchResult } from "../../src/interfaces/orchestration.js";
import {
  ModelTier,
  TeamRouter,
  type RouterTarget,
} from "../../src/orchestration/router.js";

type ExecutionEntry = {
  readonly agent: string;
  readonly modelTier: ModelTier;
  readonly order: number;
  readonly status: "completed" | "failed" | "error";
  readonly output?: string;
};

type MockProviderCall = {
  readonly provider: RouterTarget;
  readonly prompt: string;
  readonly modelTier: ModelTier;
};

interface MockProvider {
  readonly target: RouterTarget;
  readonly calls: MockProviderCall[];
  execute(prompt: string, modelTier: ModelTier): Promise<string>;
}

interface WorkflowSimulationResult {
  readonly analysis: ReturnType<typeof understandIntent>;
  readonly decisionPoint: Options131 | null;
  readonly selectedOption: OptionEntry | null;
  readonly route: TeamDispatchResult;
  readonly governanceChecks: readonly GovernanceCheckResult[];
  readonly toolDecisions: readonly ToolFabricResult[];
  readonly providerCalls: readonly MockProviderCall[];
}

const TEMP_DIRS: string[] = [];

function makeTempProjectDir(): string {
  const dir = join(
    tmpdir(),
    `omg-e2e-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
  TEMP_DIRS.push(dir);
  return dir;
}

function createMockProvider(target: RouterTarget): MockProvider {
  const calls: MockProviderCall[] = [];

  return {
    target,
    calls,
    async execute(prompt: string, modelTier: ModelTier): Promise<string> {
      calls.push({ provider: target, prompt, modelTier });
      return `mock:${target}:${modelTier}:${prompt}`;
    },
  };
}

function createProviderMap(): Record<RouterTarget, MockProvider> {
  return {
    codex: createMockProvider("codex"),
    gemini: createMockProvider("gemini"),
    ccg: createMockProvider("ccg"),
  };
}

function buildRoutingSignals(
  analysis: ReturnType<typeof understandIntent>,
): Required<TeamDispatchRequest>["routingSignals"] {
  switch (analysis.intent) {
    case "trivial":
      return { files: 1, loc: 5, deps: 0, errors: 0 };
    case "architectural":
      return { files: 12, loc: 1_600, deps: 12, errors: 5 };
    case "complex":
      return { files: 10, loc: 1_100, deps: 10, errors: 5 };
    case "moderate":
      return { files: 3, loc: 240, deps: 2, errors: 0 };
    case "simple":
    case "research":
    default:
      return { files: 2, loc: 120, deps: 1, errors: 0 };
  }
}

function getExecution(route: TeamDispatchResult): readonly ExecutionEntry[] {
  const execution = route.evidence.execution;
  return Array.isArray(execution) ? (execution as ExecutionEntry[]) : [];
}

async function simulateWorkflow(
  prompt: string,
  selectedOptionIndex?: number,
): Promise<WorkflowSimulationResult> {
  const analysis = understandIntent(prompt);
  const decisionPoint = resolveDecisionPoint(analysis);
  const selectedOption =
    decisionPoint && selectedOptionIndex !== undefined
      ? decisionPoint.options[selectedOptionIndex] ?? null
      : null;
  const providerMap = createProviderMap();
  const governanceChecks: GovernanceCheckResult[] = [];
  const toolDecisions: ToolFabricResult[] = [];
  const fabric = new ToolFabric(makeTempProjectDir());

  fabric.registerLane("provider-dispatch", {
    allowedTools: ["provider.dispatch"],
    requiresAttestation: true,
    evidenceRequired: ["intent", "routing", "provider"],
  });
  fabric.registerLane("architectural-review", {
    allowedTools: ["provider.dispatch"],
    requiresSignedApproval: true,
    requiresAttestation: true,
    evidenceRequired: ["intent", "routing", "provider"],
  });

  const request: TeamDispatchRequest = {
    target: "auto",
    problem: selectedOption
      ? `${prompt}\n\nSelected option: ${selectedOption.label} — ${selectedOption.description}`
      : prompt,
    context: [
      `intent=${analysis.intent}`,
      `domain=${analysis.domain}`,
      `risk=${analysis.complexity.riskLevel}`,
      selectedOption ? `user-choice=${selectedOption.label}` : undefined,
    ]
      .filter(Boolean)
      .join("\n"),
    expectedOutcome: `Return a governed mock output for: ${prompt}`,
    routingSignals: buildRoutingSignals(analysis),
  };

  const router = TeamRouter.create({
    dispatchFn: async (agentName, workerPrompt, context, modelTier) => {
      const governanceCheck = await fabric.preDispatchGovernanceCheck(
        ["intent-router", agentName, analysis.intent],
        `workflow-${analysis.intent}-${agentName}`,
      );
      governanceChecks.push(governanceCheck);

      const lane =
        analysis.intent === "architectural"
          ? "architectural-review"
          : "provider-dispatch";
      const decision = await fabric.executeTool(
        "provider.dispatch",
        {
          provider: agentName,
          attested: true,
          signedApproval: analysis.intent === "architectural",
          evidence: {
            intent: analysis.intent,
            routing: context.routingSignals ?? {},
            provider: agentName,
          },
        },
        lane,
        async () => providerMap[agentName].execute(workerPrompt, modelTier),
        { provider: agentName },
      );
      toolDecisions.push(decision.decision);

      return {
        output: String(decision.output),
        exitCode: 0,
      };
    },
  });

  try {
    const route = await router.route(request);
    const providerCalls = Object.values(providerMap).flatMap((provider) =>
      provider.calls,
    );

    return {
      analysis,
      decisionPoint,
      selectedOption,
      route,
      governanceChecks,
      toolDecisions,
      providerCalls,
    };
  } finally {
    fabric.close();
  }
}

afterEach(() => {
  while (TEMP_DIRS.length > 0) {
    const dir = TEMP_DIRS.pop();
    if (dir) {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

describe("full workflow E2E simulation", () => {
  test("trivial prompt flows from intent to haiku mock output", async () => {
    const result = await simulateWorkflow("fix typo in button");
    const execution = getExecution(result.route);

    expect(result.analysis.intent).toBe("trivial");
    expect(result.route.evidence.model_tier).toBe(ModelTier.Haiku);
    expect(result.route.evidence.selected_target).toBe("gemini");
    expect(result.governanceChecks).toHaveLength(1);
    expect(result.governanceChecks[0]?.ledgerEntry).toBeTruthy();
    expect(result.toolDecisions[0]).toMatchObject({
      action: "allow",
      lane: "provider-dispatch",
      tool: "provider.dispatch",
    });
    expect(result.providerCalls).toEqual([
      expect.objectContaining({
        provider: "gemini",
        modelTier: ModelTier.Haiku,
      }),
    ]);
    expect(execution).toHaveLength(1);
    expect(execution[0]?.output).toContain("mock:gemini:haiku:fix typo in button");
  });

  test("complex prompt escalates to opus with governance before mock provider output", async () => {
    const result = await simulateWorkflow("redesign auth system");
    const execution = getExecution(result.route);

    expect(result.analysis.intent).toBe("architectural");
    expect(result.route.evidence.model_tier).toBe(ModelTier.Opus);
    expect(result.route.evidence.selected_target).toBe("codex");
    expect(result.governanceChecks[0]?.allowed).toBe(true);
    expect(result.governanceChecks[0]?.ledgerEntry).toBeTruthy();
    expect(result.toolDecisions[0]).toMatchObject({
      action: "allow",
      lane: "architectural-review",
      tool: "provider.dispatch",
    });
    expect(result.providerCalls).toEqual([
      expect.objectContaining({
        provider: "codex",
        modelTier: ModelTier.Opus,
      }),
    ]);
    expect(execution[0]?.output).toContain("mock:codex:opus:redesign auth system");
  });

  test("ambiguous prompt presents 1:3:1 options, records user choice, and returns governed mock output", async () => {
    const result = await simulateWorkflow("do something with API", 1);
    const execution = getExecution(result.route);

    expect(result.analysis.ambiguities.length).toBeGreaterThan(0);
    expect(result.decisionPoint).not.toBeNull();
    expect(result.decisionPoint?.options).toHaveLength(3);
    expect(result.decisionPoint?.options.filter((option) => option.recommended)).toHaveLength(1);
    expect(result.selectedOption?.label).toBe("Service layer pattern");
    expect(result.route.evidence.model_tier).toBe(ModelTier.Sonnet);
    expect(result.route.evidence.selected_target).toBe("codex");
    expect(result.governanceChecks[0]?.ledgerEntry).toBeTruthy();
    expect(result.toolDecisions[0]).toMatchObject({
      action: "allow",
      lane: "provider-dispatch",
      tool: "provider.dispatch",
    });
    expect(result.providerCalls[0]?.prompt).toContain("Selected option: Service layer pattern");
    expect(execution[0]?.output).toContain("mock:codex:sonnet:do something with API");
    expect(execution[0]?.output).toContain("Selected option: Service layer pattern");
  });
});
