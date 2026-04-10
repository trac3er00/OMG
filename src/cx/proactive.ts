import type { IntentAnalysis } from "../intent/index.js";
import { resolveDecisionPoint, type Options131 } from "../intent/options.js";

export type IntentResult = IntentAnalysis;

export interface ClarifyingQuestion {
  readonly question: string;
  readonly reason: string;
}

export interface ProactiveExecutionContext {
  readonly prompt?: string;
}

export type ExecutionMode = "execute" | "clarify" | "plan";

export interface ExecutionDecision {
  readonly mode: ExecutionMode;
  readonly executeImmediately: boolean;
  readonly clarifyingQuestion: ClarifyingQuestion | null;
  readonly showPlan: boolean;
  readonly plan: Options131 | null;
  readonly context: ProactiveExecutionContext;
}

function buildRiskAwarePlan(intent: IntentResult): Options131 {
  return {
    problem:
      intent.ambiguities[0] ??
      `This ${intent.domain} request carries ${intent.complexity.riskLevel} risk and should be reviewed before execution.`,
    options: [
      {
        label: "Minimal scoped change",
        description:
          "Limit the change to the smallest reversible slice before broader rollout.",
        tradeoffs: {
          pros: [
            "Keeps blast radius small and makes rollback easier if the change is wrong.",
          ],
          cons: [
            "May require follow-up work to reach the full requested outcome.",
          ],
        },
        recommended: true,
      },
      {
        label: "Staged execution",
        description:
          "Break the work into checkpoints with validation between each step.",
        tradeoffs: {
          pros: [
            "Improves observability and creates explicit stop points before risky mutations.",
          ],
          cons: [
            "Takes longer because each stage needs its own verification step.",
          ],
        },
        recommended: false,
      },
      {
        label: "Full immediate execution",
        description:
          "Apply the full change in one pass after explicit approval.",
        tradeoffs: {
          pros: [
            "Delivers the requested outcome fastest once the plan is approved.",
          ],
          cons: [
            "Highest blast radius if assumptions are wrong or rollback is difficult.",
          ],
        },
        recommended: false,
      },
    ],
  };
}

function isTrivialOrSimple(intent: IntentResult): boolean {
  return intent.intent === "trivial" || intent.intent === "simple";
}

function needsClarification(intent: IntentResult): boolean {
  return intent.ambiguities.length > 0 && intent.clarifyingQuestions.length > 0;
}

function needsPlan(intent: IntentResult): boolean {
  return (
    intent.complexity.riskLevel === "high" ||
    intent.intent === "complex" ||
    intent.intent === "architectural" ||
    intent.intent === "research" ||
    intent.complexity.effort === "high"
  );
}

export class ProactiveExecutor {
  shouldExecuteImmediately(intent: IntentResult): boolean {
    return isTrivialOrSimple(intent) && !needsClarification(intent);
  }

  shouldAskClarification(intent: IntentResult): ClarifyingQuestion | null {
    if (!needsClarification(intent)) {
      return null;
    }

    return {
      question: intent.clarifyingQuestions[0]!,
      reason: intent.ambiguities[0] ?? "Task scope is ambiguous.",
    };
  }

  shouldShowPlan(intent: IntentResult): boolean {
    return !needsClarification(intent) && needsPlan(intent);
  }

  execute(
    intent: IntentResult,
    context: ProactiveExecutionContext = {},
  ): ExecutionDecision {
    const clarifyingQuestion = this.shouldAskClarification(intent);
    const showPlan = this.shouldShowPlan(intent);
    const plan = showPlan
      ? (resolveDecisionPoint(intent) ?? buildRiskAwarePlan(intent))
      : null;
    const executeImmediately =
      clarifyingQuestion === null &&
      !showPlan &&
      this.shouldExecuteImmediately(intent);

    return {
      mode: clarifyingQuestion ? "clarify" : showPlan ? "plan" : "execute",
      executeImmediately,
      clarifyingQuestion,
      showPlan,
      plan,
      context,
    };
  }
}
