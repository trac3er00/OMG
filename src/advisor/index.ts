import type { IntentAnalysis } from "../intent/index.js";
import { shouldTriggerAdvisor, type AdvisorContext } from "./triggers.js";

export interface AdvisorRecommendation {
  readonly recommendation: string;
  readonly rationale: string;
  readonly alternatives: string[];
  readonly risks: string[];
  readonly depth: number;
}

export function getAdvisorRecommendation(
  intent: IntentAnalysis & AdvisorContext,
  depth: number = 0,
): AdvisorRecommendation | null {
  if (!shouldTriggerAdvisor(intent, depth)) {
    return null;
  }

  return {
    recommendation: `For this ${intent.intent} task, consider breaking it into smaller incremental changes`,
    rationale: `${intent.intent} tasks with ${intent.complexity.riskLevel} risk benefit from staged approaches`,
    alternatives: [
      "Break into smaller atomic tasks",
      "Create a design document first",
      "Spike with a proof-of-concept",
    ],
    risks: intent.complexity.signals.map((s) => `Risk signal: ${s}`),
    depth,
  };
}
