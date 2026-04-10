import type {
  BudgetEnvelope as BudgetEnvelopeSnapshot,
  RoutingSignals,
  TeamDispatchRequest,
  TeamDispatchResult,
} from "../interfaces/orchestration.js";

export type RouterTarget = "codex" | "gemini" | "ccg";
export type RouterRequestedTarget = RouterTarget | "auto";

export enum ModelTier {
  Haiku = "haiku",
  Sonnet = "sonnet",
  Opus = "opus",
}

export interface RouterWorkerTask {
  readonly agentName: RouterTarget;
  readonly modelTier: ModelTier;
  readonly prompt: string;
  readonly order?: number;
}

export interface RouterWorkerResult {
  readonly agent: string;
  readonly modelTier: ModelTier;
  readonly order: number;
  readonly status: "completed" | "failed" | "error";
  readonly output?: string;
  readonly error?: string;
  readonly exitCode?: number;
}

export interface TeamRouterDispatchResult {
  readonly output?: string;
  readonly error?: string;
  readonly exitCode?: number;
}

export type TeamRouterDispatchFn = (
  agentName: RouterTarget,
  prompt: string,
  context: TeamDispatchRequest,
  modelTier: ModelTier,
) => Promise<TeamRouterDispatchResult>;

export interface TeamRouterOptions {
  readonly dispatchFn?: TeamRouterDispatchFn;
}

const COST_TIER: Readonly<Record<RouterTarget, number>> = {
  gemini: 1,
  codex: 2,
  ccg: 3,
};

const CODE_SIGNALS: readonly string[] = [
  "build",
  "code",
  "component",
  "react",
  "typescript",
  "javascript",
  "bug",
  "api",
  "backend",
  "auth",
];

const INFRA_SIGNALS: readonly string[] = [
  "infra",
  "infrastructure",
  "deploy",
  "kubernetes",
  "docker",
  "terraform",
  "helm",
  "ci",
  "pipeline",
];

const RESEARCH_SIGNALS: readonly string[] = [
  "research",
  "investigate",
  "analysis",
  "analyze",
  "compare",
  "study",
  "survey",
  "report",
];

const SIMPLE_LOC_MAX = 10;
const STANDARD_FILES_MAX = 3;
const STANDARD_LOC_MAX = 500;
const STANDARD_DEPS_MAX = 5;
const COMPLEX_FILES_MIN = 10;
const COMPLEX_LOC_MIN = 1_000;
const COMPLEX_DEPS_MIN = 10;
const COMPLEX_ERRORS_MIN = 5;
const BUDGET_DOWNGRADE_THRESHOLD = 0.2;

interface NormalizedRoutingSignals {
  readonly files: number;
  readonly loc: number;
  readonly deps: number;
  readonly errors: number;
}

interface TierSelection {
  readonly tier: ModelTier;
  readonly baseTier: ModelTier;
  readonly reason: string;
  readonly downgradedForBudget: boolean;
  readonly budgetRemainingRatio: number | null;
  readonly signals: NormalizedRoutingSignals;
}

function normalizeSignals(
  request: TeamDispatchRequest,
): NormalizedRoutingSignals {
  const signals: RoutingSignals = request.routingSignals ?? {};
  return {
    files: signals.files ?? request.files?.length ?? 0,
    loc: signals.loc ?? 0,
    deps: signals.deps ?? 0,
    errors: signals.errors ?? 0,
  };
}

function inferBaseTier(signals: NormalizedRoutingSignals): {
  readonly tier: ModelTier;
  readonly reason: string;
} {
  const isComplex =
    signals.files >= COMPLEX_FILES_MIN ||
    signals.loc >= COMPLEX_LOC_MIN ||
    signals.deps >= COMPLEX_DEPS_MIN ||
    signals.errors >= COMPLEX_ERRORS_MIN;
  if (isComplex) {
    return {
      tier: ModelTier.Opus,
      reason: "complex routing signals require the highest-capability tier",
    };
  }

  const isSimple =
    signals.files === 1 &&
    signals.loc <= SIMPLE_LOC_MAX &&
    signals.deps === 0 &&
    signals.errors === 0;
  if (isSimple) {
    return {
      tier: ModelTier.Haiku,
      reason: "simple routing signals fit the low-cost tier",
    };
  }

  const isStandard =
    signals.files >= 1 &&
    signals.files <= STANDARD_FILES_MAX &&
    signals.loc >= SIMPLE_LOC_MAX &&
    signals.loc <= STANDARD_LOC_MAX &&
    signals.deps <= STANDARD_DEPS_MAX &&
    signals.errors < COMPLEX_ERRORS_MIN;
  if (isStandard) {
    return {
      tier: ModelTier.Sonnet,
      reason: "standard routing signals fit the default tier",
    };
  }

  return {
    tier: ModelTier.Sonnet,
    reason: "ambiguous routing signals default to the standard tier",
  };
}

function downgradeTier(tier: ModelTier): ModelTier {
  if (tier === ModelTier.Opus) {
    return ModelTier.Sonnet;
  }
  if (tier === ModelTier.Sonnet) {
    return ModelTier.Haiku;
  }
  return ModelTier.Haiku;
}

function budgetRemainingRatio(budget?: BudgetEnvelopeSnapshot): number | null {
  if (budget === undefined) {
    return null;
  }

  const ratios = [
    [budget.tokenLimit, budget.tokensUsed],
    [budget.cpuSecondsLimit, budget.cpuSecondsUsed],
    [budget.memoryMbLimit, budget.memoryMbPeak],
    [budget.wallTimeSecondsLimit, budget.wallTimeSecondsUsed],
    [budget.networkBytesLimit, budget.networkBytesUsed],
  ]
    .filter(([limit]) => limit > 0)
    .map(([limit, used]) => Math.max(0, (limit - used) / limit));

  if (ratios.length === 0) {
    return null;
  }

  return Math.min(...ratios);
}

function selectModelTier(request: TeamDispatchRequest): TierSelection {
  const signals = normalizeSignals(request);
  const base = inferBaseTier(signals);
  const remainingRatio = budgetRemainingRatio(request.budget);
  const shouldDowngrade =
    remainingRatio !== null && remainingRatio < BUDGET_DOWNGRADE_THRESHOLD;
  const tier = shouldDowngrade ? downgradeTier(base.tier) : base.tier;
  const reason = shouldDowngrade
    ? `${base.reason}; downgraded for budget pressure`
    : base.reason;

  return {
    tier,
    baseTier: base.tier,
    reason,
    downgradedForBudget: shouldDowngrade,
    budgetRemainingRatio: remainingRatio,
    signals,
  };
}

function rankTargetsByCost(targets: readonly RouterTarget[]): RouterTarget[] {
  return [...targets].sort((left, right) => COST_TIER[left] - COST_TIER[right]);
}

function inferTarget(problem: string): {
  readonly target: RouterTarget;
  readonly reason: string;
} {
  const normalized = problem.toLowerCase();

  const explicitCodex = /\bcodex\b/.test(normalized);
  const explicitGemini = /\bgemini\b/.test(normalized);
  const explicitCcg =
    /\bccg\b/.test(normalized) ||
    normalized.includes("tri-track") ||
    normalized.includes("tri track");
  if (explicitCcg || (explicitCodex && explicitGemini)) {
    return {
      target: "ccg",
      reason: "explicitly requested multi-provider routing",
    };
  }
  if (explicitCodex) {
    return { target: "codex", reason: "explicit codex intent detected" };
  }
  if (explicitGemini) {
    return { target: "gemini", reason: "explicit gemini intent detected" };
  }

  const hasCodeSignal = CODE_SIGNALS.some((signal) =>
    normalized.includes(signal),
  );
  const hasInfraSignal = INFRA_SIGNALS.some((signal) =>
    normalized.includes(signal),
  );
  const hasResearchSignal = RESEARCH_SIGNALS.some((signal) =>
    normalized.includes(signal),
  );

  if (hasInfraSignal || hasCodeSignal) {
    return {
      target: "codex",
      reason: "domain signal matched code/infra workload",
    };
  }

  if (hasResearchSignal) {
    return {
      target: "gemini",
      reason: "domain signal matched research workload",
    };
  }

  const [lowestCostTarget] = rankTargetsByCost(["codex", "gemini", "ccg"]);
  return {
    target: lowestCostTarget,
    reason: "no strong signal detected; selected lowest-cost target",
  };
}

function toStatus(
  result: TeamRouterDispatchResult,
): RouterWorkerResult["status"] {
  if (result.error !== undefined) {
    return "error";
  }
  if (result.exitCode !== undefined && result.exitCode !== 0) {
    return "failed";
  }
  return "completed";
}

function defaultDispatch(): TeamRouterDispatchFn {
  return async (_agentName, _prompt, _context, _modelTier) => ({
    output: "dispatch skipped (no dispatchFn configured)",
    exitCode: 0,
  });
}

export class TeamRouter {
  static create(options: TeamRouterOptions = {}): TeamRouter {
    return new TeamRouter(options.dispatchFn ?? defaultDispatch());
  }

  private readonly dispatchFn: TeamRouterDispatchFn;

  constructor(dispatchFn: TeamRouterDispatchFn) {
    this.dispatchFn = dispatchFn;
  }

  async route(request: TeamDispatchRequest): Promise<TeamDispatchResult> {
    const requestedTarget = request.target
      .toLowerCase()
      .trim() as RouterRequestedTarget;
    const selection = this.selectTarget(requestedTarget, request.problem);
    const tierSelection = selectModelTier(request);
    const workers = this.buildWorkers(
      selection.target,
      request,
      tierSelection.tier,
    );
    const parallel = selection.target === "ccg";
    const execution = await this.executeWorkers(workers, request, parallel);

    const findings: string[] = [
      `Target router selected: ${selection.target}`,
      `Reason: ${selection.reason}`,
      `Model tier selected: ${tierSelection.tier}`,
      `Model tier reason: ${tierSelection.reason}`,
      `Execution mode: ${parallel ? "parallel" : "sequential"}`,
    ];

    const actions = parallel
      ? [
          "Run codex and gemini in parallel",
          "Synthesize cross-functional findings",
        ]
      : [
          "Run focused single-agent execution",
          "Return concrete action plan and verification steps",
        ];

    return {
      status: "ok",
      findings,
      actions,
      evidence: {
        requested_target: requestedTarget,
        selected_target: selection.target,
        selection_reason: selection.reason,
        model_tier: tierSelection.tier,
        base_model_tier: tierSelection.baseTier,
        model_tier_reason: tierSelection.reason,
        model_tier_budget_downgraded: tierSelection.downgradedForBudget,
        budget_remaining_ratio: tierSelection.budgetRemainingRatio,
        routing_signals: tierSelection.signals,
        cost_ranking: rankTargetsByCost(["codex", "gemini", "ccg"]),
        parallel_execution: parallel,
        execution,
      },
    };
  }

  private selectTarget(
    requestedTarget: RouterRequestedTarget,
    problem: string,
  ): { readonly target: RouterTarget; readonly reason: string } {
    if (requestedTarget !== "auto") {
      if (
        requestedTarget === "codex" ||
        requestedTarget === "gemini" ||
        requestedTarget === "ccg"
      ) {
        return { target: requestedTarget, reason: "explicit target requested" };
      }
      return { target: "codex", reason: "invalid target fallbacked to codex" };
    }
    return inferTarget(problem);
  }

  private buildWorkers(
    target: RouterTarget,
    request: TeamDispatchRequest,
    modelTier: ModelTier,
  ): RouterWorkerTask[] {
    const sharedContext =
      request.context.length > 0 ? `\n\nContext:\n${request.context}` : "";
    const basePrompt = `${request.problem}${sharedContext}`;

    if (target === "ccg") {
      return [
        {
          agentName: "codex",
          modelTier,
          prompt: `Backend/code track:\n${basePrompt}`,
          order: 1,
        },
        {
          agentName: "gemini",
          modelTier,
          prompt: `Research/UI track:\n${basePrompt}`,
          order: 2,
        },
      ];
    }
    return [{ agentName: target, modelTier, prompt: basePrompt, order: 1 }];
  }

  private async executeWorkers(
    workers: readonly RouterWorkerTask[],
    request: TeamDispatchRequest,
    parallel: boolean,
  ): Promise<readonly RouterWorkerResult[]> {
    return parallel
      ? this.executeWorkersParallel(workers, request)
      : this.executeWorkersSequential(workers, request);
  }

  private async executeWorkersSequential(
    workers: readonly RouterWorkerTask[],
    request: TeamDispatchRequest,
  ): Promise<readonly RouterWorkerResult[]> {
    const sorted = [...workers].sort(
      (left, right) => (left.order ?? 0) - (right.order ?? 0),
    );
    const results: RouterWorkerResult[] = [];

    for (const worker of sorted) {
      const result = await this.dispatchFn(
        worker.agentName,
        worker.prompt,
        request,
        worker.modelTier,
      );
      const workerResult: RouterWorkerResult = {
        agent: worker.agentName,
        modelTier: worker.modelTier,
        order: worker.order ?? 0,
        status: toStatus(result),
      };
      if (result.output !== undefined) {
        Object.assign(workerResult, { output: result.output });
      }
      if (result.error !== undefined) {
        Object.assign(workerResult, { error: result.error });
      }
      if (result.exitCode !== undefined) {
        Object.assign(workerResult, { exitCode: result.exitCode });
      }
      results.push(workerResult);
    }

    return results;
  }

  private async executeWorkersParallel(
    workers: readonly RouterWorkerTask[],
    request: TeamDispatchRequest,
  ): Promise<readonly RouterWorkerResult[]> {
    const sorted = [...workers].sort(
      (left, right) => (left.order ?? 0) - (right.order ?? 0),
    );

    return Promise.all(
      sorted.map(async (worker): Promise<RouterWorkerResult> => {
        const result = await this.dispatchFn(
          worker.agentName,
          worker.prompt,
          request,
          worker.modelTier,
        );
        const workerResult: RouterWorkerResult = {
          agent: worker.agentName,
          modelTier: worker.modelTier,
          order: worker.order ?? 0,
          status: toStatus(result),
        };
        if (result.output !== undefined) {
          Object.assign(workerResult, { output: result.output });
        }
        if (result.error !== undefined) {
          Object.assign(workerResult, { error: result.error });
        }
        if (result.exitCode !== undefined) {
          Object.assign(workerResult, { exitCode: result.exitCode });
        }
        return workerResult;
      }),
    );
  }
}
