import type { RouterTarget } from "./router.js";

export type TaskComplexity = "simple" | "moderate" | "hard" | "expert";

export interface EscalationConfig {
  enabled: boolean;
  complexityThreshold: TaskComplexity;
  defaultModel: string;
  escalatedModel: string;
  maxEscalationsPerSession: number;
}

export const DEFAULT_ESCALATION_CONFIG: EscalationConfig = {
  enabled: true,
  complexityThreshold: "hard",
  defaultModel: "claude-sonnet",
  escalatedModel: "claude-opus",
  maxEscalationsPerSession: 10,
};

export interface EscalationEvidence {
  task: string;
  complexity: TaskComplexity;
  selectedModel: string;
  escalated: boolean;
  reason: string;
}

export interface EscalationBudgetSnapshot {
  escalationCount: number;
  estimatedCostMultiplier: number;
  cumulativeCostMultiplier: number;
}

export interface EscalationResult {
  escalated: boolean;
  model: string;
  reason?: string;
  estimatedCostMultiplier: number;
  budget: EscalationBudgetSnapshot;
  evidence: EscalationEvidence;
}

const COMPLEXITY_ORDER: readonly TaskComplexity[] = [
  "simple",
  "moderate",
  "hard",
  "expert",
];

const COMPLEXITY_SIGNALS: ReadonlyArray<{
  readonly pattern: RegExp;
  readonly weight: number;
}> = [
  {
    pattern:
      /\barchitecture\b|\bdistributed\b|\bscal(?:e|ing)\b|\bmigration\b/i,
    weight: 2,
  },
  {
    pattern:
      /\bsecurity\b|\bauth(?:entication)?\b|\bauthori[sz]ation\b|\bcompliance\b/i,
    weight: 2,
  },
  {
    pattern: /\balgorithm\b|\bheuristic\b|\boptimization\b|\bcomplexity\b/i,
    weight: 2,
  },
  {
    pattern: /\bplanner\b|\borchestrat(?:e|ion)\b|\bmulti-model\b|\brouter\b/i,
    weight: 1,
  },
  {
    pattern:
      /\bconcurrency\b|\bparallel\b|\bsynchroni[sz]ation\b|\brace condition\b/i,
    weight: 2,
  },
  {
    pattern: /\brefactor\b|\bintegration\b|\bverification\b|\bevidence\b/i,
    weight: 1,
  },
  {
    pattern: /\bincident\b|\breliability\b|\bfault\b|\brollback\b/i,
    weight: 1,
  },
];

const EXPERT_SIGNALS: readonly RegExp[] = [
  /\bformal verification\b/i,
  /\bcryptograph(?:y|ic)\b/i,
  /\bzero[- ]downtime\b/i,
  /\bconsensus\b/i,
  /\bsafety[- ]critical\b/i,
];

const ROUTER_COST_TIER: Readonly<Record<RouterTarget, number>> = {
  gemini: 1,
  codex: 2,
  ccg: 3,
};

const MODEL_COST_MULTIPLIER: Readonly<Record<string, number>> = {
  gemini: ROUTER_COST_TIER.gemini,
  codex: ROUTER_COST_TIER.codex,
  ccg: ROUTER_COST_TIER.ccg,
  "claude-sonnet": 2,
  "claude-opus": 4,
};

function normalizeTaskText(task: {
  description: string;
  keywords?: string[];
}): string {
  return [task.description, ...(task.keywords ?? [])].join(" ").toLowerCase();
}

function compareComplexity(
  left: TaskComplexity,
  right: TaskComplexity,
): number {
  return COMPLEXITY_ORDER.indexOf(left) - COMPLEXITY_ORDER.indexOf(right);
}

function estimateCostMultiplier(
  defaultModel: string,
  selectedModel: string,
): number {
  const defaultTier = MODEL_COST_MULTIPLIER[defaultModel] ?? 1;
  const selectedTier =
    MODEL_COST_MULTIPLIER[selectedModel] ?? Math.max(defaultTier, 2);
  return Number((selectedTier / defaultTier).toFixed(2));
}

export function classifyTaskComplexity(task: {
  description: string;
  keywords?: string[];
}): TaskComplexity {
  const normalized = normalizeTaskText(task);
  if (normalized.trim().length === 0) {
    return "simple";
  }

  if (EXPERT_SIGNALS.some((pattern) => pattern.test(normalized))) {
    return "expert";
  }

  const score = COMPLEXITY_SIGNALS.reduce((total, signal) => {
    return signal.pattern.test(normalized) ? total + signal.weight : total;
  }, 0);

  if (score >= 6) {
    return "expert";
  }
  if (score >= 3) {
    return "hard";
  }
  if (score >= 1) {
    return "moderate";
  }
  return "simple";
}

export function shouldEscalate(
  complexity: TaskComplexity,
  config: EscalationConfig,
): boolean {
  if (!config.enabled) {
    return false;
  }
  return compareComplexity(complexity, config.complexityThreshold) >= 0;
}

export function getEscalationResult(
  task: { description: string; keywords?: string[] },
  config: EscalationConfig = DEFAULT_ESCALATION_CONFIG,
): EscalationResult {
  const complexity = classifyTaskComplexity(task);
  const escalated = shouldEscalate(complexity, config);
  const model = escalated ? config.escalatedModel : config.defaultModel;
  const reason = escalated
    ? `Task classified as ${complexity}; escalated from ${config.defaultModel} to ${config.escalatedModel}`
    : `Task classified as ${complexity}; kept on ${config.defaultModel}`;
  const estimatedCostMultiplier = estimateCostMultiplier(
    config.defaultModel,
    model,
  );

  return {
    escalated,
    model,
    reason,
    estimatedCostMultiplier,
    budget: {
      escalationCount: escalated ? 1 : 0,
      estimatedCostMultiplier,
      cumulativeCostMultiplier: estimatedCostMultiplier,
    },
    evidence: {
      task: task.description,
      complexity,
      selectedModel: model,
      escalated,
      reason,
    },
  };
}

export class EscalationTracker {
  private escalationCount = 0;

  private cumulativeCostMultiplier = 0;

  private lastEstimatedCostMultiplier = 1;

  private readonly decisions: EscalationEvidence[] = [];

  constructor(
    private readonly config: EscalationConfig = DEFAULT_ESCALATION_CONFIG,
  ) {}

  evaluateTask(task: {
    description: string;
    keywords?: string[];
  }): EscalationResult {
    const baseResult = getEscalationResult(task, this.config);
    const capped =
      baseResult.escalated &&
      this.escalationCount >= this.config.maxEscalationsPerSession;

    const result: EscalationResult = capped
      ? {
          ...baseResult,
          escalated: false,
          model: this.config.defaultModel,
          reason: `Escalation limit reached (${this.config.maxEscalationsPerSession}/${this.config.maxEscalationsPerSession}); kept on ${this.config.defaultModel}`,
          estimatedCostMultiplier: 1,
          evidence: {
            ...baseResult.evidence,
            escalated: false,
            selectedModel: this.config.defaultModel,
            reason: `Escalation limit reached (${this.config.maxEscalationsPerSession}/${this.config.maxEscalationsPerSession}); kept on ${this.config.defaultModel}`,
          },
          budget: {
            escalationCount: this.escalationCount,
            estimatedCostMultiplier: 1,
            cumulativeCostMultiplier: this.cumulativeCostMultiplier,
          },
        }
      : baseResult;

    if (result.escalated) {
      this.escalationCount += 1;
    }
    this.lastEstimatedCostMultiplier = result.estimatedCostMultiplier;
    this.cumulativeCostMultiplier += result.estimatedCostMultiplier;
    this.decisions.push(result.evidence);

    return {
      ...result,
      budget: {
        escalationCount: this.escalationCount,
        estimatedCostMultiplier: result.estimatedCostMultiplier,
        cumulativeCostMultiplier: Number(
          this.cumulativeCostMultiplier.toFixed(2),
        ),
      },
    };
  }

  getBudgetSnapshot(): EscalationBudgetSnapshot {
    return {
      escalationCount: this.escalationCount,
      estimatedCostMultiplier: this.lastEstimatedCostMultiplier,
      cumulativeCostMultiplier: Number(
        this.cumulativeCostMultiplier.toFixed(2),
      ),
    };
  }

  getEvidence(): readonly EscalationEvidence[] {
    return [...this.decisions];
  }
}
