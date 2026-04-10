import {
  getEscalationResult,
  type EscalationConfig,
  DEFAULT_ESCALATION_CONFIG,
} from "./escalation.js";

export interface AutoEscalationRequest {
  taskDescription: string;
  userOverrideModel?: string;
  config?: Partial<EscalationConfig>;
}

export interface AutoEscalationDecision {
  model: string;
  escalated: boolean;
  overridden: boolean;
  reason: string;
  estimatedCostMultiplier: number;
}

export interface EscalationCostTracker {
  totalEscalations: number;
  totalCostMultiplier: number;
  add(multiplier: number): void;
  summary(): { totalEscalations: number; averageCostMultiplier: number };
}

export function createCostTracker(): EscalationCostTracker {
  const tracker: EscalationCostTracker = {
    totalEscalations: 0,
    totalCostMultiplier: 0,
    add(multiplier: number) {
      this.totalEscalations++;
      this.totalCostMultiplier += multiplier;
    },
    summary() {
      return {
        totalEscalations: this.totalEscalations,
        averageCostMultiplier:
          this.totalEscalations > 0
            ? this.totalCostMultiplier / this.totalEscalations
            : 1.0,
      };
    },
  };
  return tracker;
}

export function decideEscalation(
  request: AutoEscalationRequest,
  tracker?: EscalationCostTracker,
): AutoEscalationDecision {
  const config: EscalationConfig = {
    ...DEFAULT_ESCALATION_CONFIG,
    ...request.config,
  };

  if (request.userOverrideModel) {
    return {
      model: request.userOverrideModel,
      escalated: false,
      overridden: true,
      reason: `User override: ${request.userOverrideModel}`,
      estimatedCostMultiplier: 1.0,
    };
  }

  const result = getEscalationResult(
    { description: request.taskDescription },
    config,
  );

  if (result.escalated && tracker) {
    tracker.add(result.estimatedCostMultiplier);
  }

  return {
    model: result.model,
    escalated: result.escalated,
    overridden: false,
    reason:
      result.reason ??
      (result.escalated
        ? "Auto-escalated: hard task"
        : "Default model sufficient"),
    estimatedCostMultiplier: result.estimatedCostMultiplier,
  };
}
