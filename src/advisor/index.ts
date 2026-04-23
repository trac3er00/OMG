import { join } from "node:path";
import type { IntentAnalysis } from "../intent/index.js";
import type { FidelityResult } from "../intent/fidelity-checker.js";
import {
  getEscalationResult,
  type EscalationResult,
} from "../orchestration/escalation.js";
import type { SanitizedContent } from "../security/external-firewall.js";
import type { TrustScore } from "../security/trust-scoring.js";
import { appendJsonLine } from "../state/atomic-io.js";
import {
  shouldTriggerAdvisor,
  type AdvisorContext as TriggerAdvisorContext,
} from "./triggers.js";

export interface AdvisorRecommendation {
  readonly recommendation: string;
  readonly rationale: string;
  readonly alternatives: string[];
  readonly risks: string[];
  readonly depth: number;
}

export type AdvisorDecision = "proceed" | "clarify" | "escalate" | "abort";

export interface AdvisorContext {
  readonly goal: string;
  readonly fidelityResult?: FidelityResult;
  readonly trustScore?: TrustScore;
  readonly sanitizationResult?: SanitizedContent;
  readonly round?: number;
}

export interface AdvisorOutput {
  readonly decision: AdvisorDecision;
  readonly reason: string;
  readonly clarificationQuestion?: string;
  readonly escalationReason?: string;
  readonly confidence: number;
}

interface DecisionLogEntry {
  readonly timestamp: string;
  readonly decision: AdvisorDecision;
  readonly goal: string;
  readonly reason: string;
  readonly clarificationQuestion?: string;
  readonly escalationReason?: string;
  readonly confidence: number;
  readonly signals: {
    readonly fidelity: FidelityResult | null;
    readonly trust: TrustScore | null;
    readonly sanitization: {
      readonly blocked: boolean;
      readonly wasTruncated: boolean;
      readonly injectionPatternsFound: readonly string[];
      readonly source: string;
      readonly contentBytes: number;
    } | null;
    readonly escalation: EscalationResult;
  };
}

const DEFAULT_CLARIFICATION_QUESTION =
  "What single concrete outcome should count as done for this goal?";

function getDecisionPath(decision: AdvisorDecision): string {
  const timestamp = new Date().toISOString().replace(/[:.]/gu, "-");
  return join(
    process.cwd(),
    ".omg",
    "decisions",
    `${timestamp}-${decision}.json`,
  );
}

function getEscalation(context: AdvisorContext): EscalationResult {
  return getEscalationResult({ description: context.goal });
}

function getEffectiveRound(context: AdvisorContext): number {
  return Math.max(context.round ?? context.fidelityResult?.round ?? 0, 0);
}

function emitVerboseDecision(entry: DecisionLogEntry): void {
  if (process.env.OMG_ADVISOR_VERBOSE !== "1") {
    return;
  }

  process.stderr.write(
    `[advisor:${entry.decision}] ${JSON.stringify(entry)}\n`,
  );
}

function toLoggedSanitization(
  sanitizationResult: SanitizedContent | undefined,
): DecisionLogEntry["signals"]["sanitization"] {
  if (!sanitizationResult) {
    return null;
  }

  return {
    blocked: sanitizationResult.blocked,
    wasTruncated: sanitizationResult.wasTruncated,
    injectionPatternsFound: sanitizationResult.injectionPatternsFound,
    source: sanitizationResult.source,
    contentBytes: Buffer.byteLength(sanitizationResult.content, "utf8"),
  };
}

function logDecision(
  context: AdvisorContext,
  output: AdvisorOutput,
  escalation: EscalationResult,
): void {
  const entry: DecisionLogEntry = {
    timestamp: new Date().toISOString(),
    decision: output.decision,
    goal: context.goal,
    reason: output.reason,
    confidence: output.confidence,
    signals: {
      fidelity: context.fidelityResult ?? null,
      trust: context.trustScore ?? null,
      sanitization: toLoggedSanitization(context.sanitizationResult),
      escalation,
    },
    ...(output.clarificationQuestion
      ? { clarificationQuestion: output.clarificationQuestion }
      : {}),
    ...(output.escalationReason
      ? { escalationReason: output.escalationReason }
      : {}),
  };

  try {
    appendJsonLine(getDecisionPath(output.decision), entry);
  } catch {}

  emitVerboseDecision(entry);
}

export function getAdvisorRecommendation(
  intent: IntentAnalysis & TriggerAdvisorContext,
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

export async function decide(context: AdvisorContext): Promise<AdvisorOutput> {
  const escalation = getEscalation(context);
  let output: AdvisorOutput;

  if (context.sanitizationResult?.blocked === true) {
    output = {
      decision: "abort",
      reason: "Security threat detected by the external firewall.",
      confidence: 0.99,
    };
  } else if (context.trustScore?.tier === "UNTRUSTED") {
    output = {
      decision: "escalate",
      reason: "Low-trust source requires manual escalation before execution.",
      escalationReason: `${context.trustScore.reason}. ${escalation.reason}`,
      confidence: 0.94,
    };
  } else if (context.fidelityResult?.needsClarification === true) {
    output = {
      decision: "clarify",
      reason:
        "Intent gap detected; ask a clarification question before proceeding.",
      clarificationQuestion:
        context.fidelityResult.clarificationQuestion ??
        DEFAULT_CLARIFICATION_QUESTION,
      confidence: 0.88,
    };
  } else if (getEffectiveRound(context) >= 3) {
    output = {
      decision: "proceed",
      reason: `Maximum clarification rounds reached; proceed with advisory escalation context. ${escalation.reason}`,
      confidence: 0.67,
    };
  } else {
    output = {
      decision: "proceed",
      reason: `Signals are clear enough to proceed. ${escalation.reason}`,
      confidence: escalation.escalated ? 0.86 : 0.91,
    };
  }

  logDecision(context, output, escalation);
  return output;
}

export function createAdvisor(): {
  decide: (context: AdvisorContext) => Promise<AdvisorOutput>;
} {
  return { decide };
}
