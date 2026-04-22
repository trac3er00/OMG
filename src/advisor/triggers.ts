import type { IntentAnalysis } from "../intent/index.js";

export interface AdvisorContext {
  readonly depth?: number;
  readonly _advisorGenerated?: boolean;
}

export function shouldTriggerAdvisor(
  intent: IntentAnalysis & AdvisorContext,
  depth: number = 0,
): boolean {
  if ((intent as AdvisorContext)._advisorGenerated === true) {
    return false;
  }

  if (depth >= 2) {
    return false;
  }

  if (intent.intent === "architectural") {
    return true;
  }

  if (
    intent.complexity.riskLevel === "high" &&
    (intent.intent === "complex" || intent.intent === "moderate")
  ) {
    return true;
  }

  return false;
}
