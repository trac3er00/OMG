export interface RoutingResult {
  readonly target: string | null;
  readonly confidence: number;
  readonly intent: string | null;
  readonly fallback: boolean;
  readonly timestamp: string;
}

export interface LeaderHint {
  readonly detectedIntents: readonly IntentEntry[];
}

export interface IntentEntry {
  readonly intent: string;
  readonly confidence: number;
}

export interface IntentRoutingMap {
  readonly [intent: string]: string | null;
}

export class KeywordRouter {
  private readonly routingMap: IntentRoutingMap;

  constructor(routingMap: IntentRoutingMap) {
    this.routingMap = routingMap;
  }

  route(input: LeaderHint | null): RoutingResult {
    const ts = new Date().toISOString();

    if (input === null || input.detectedIntents.length === 0) {
      return {
        target: null,
        confidence: 0,
        intent: null,
        fallback: true,
        timestamp: ts,
      };
    }

    for (const entry of input.detectedIntents) {
      if (entry.intent in this.routingMap) {
        return {
          target: this.routingMap[entry.intent] ?? null,
          confidence: entry.confidence,
          intent: entry.intent,
          fallback: false,
          timestamp: ts,
        };
      }
    }

    return {
      target: null,
      confidence: 0,
      intent: null,
      fallback: true,
      timestamp: ts,
    };
  }

  extractLeaderHint(data: Record<string, unknown>): LeaderHint | null {
    const hint = extractHintFromRecord(data);
    if (hint !== null) return hint;

    const toolOutput = data["tool_output"];
    if (isRecord(toolOutput)) {
      const fromOutput = extractHintFromRecord(toolOutput);
      if (fromOutput !== null) return fromOutput;
    }

    const hso = data["hookSpecificOutput"];
    if (isRecord(hso)) {
      const fromHso = extractHintFromRecord(hso);
      if (fromHso !== null) return fromHso;
    }

    return null;
  }
}

export interface StopGateDecision {
  readonly shouldStop: boolean;
  readonly reason: string;
  readonly blocks: readonly string[];
  readonly advisories: readonly string[];
}

export class StopGate {
  private readonly checks: readonly StopCheck[];

  constructor(checks: readonly StopCheck[]) {
    this.checks = checks;
  }

  evaluate(context: StopGateContext): StopGateDecision {
    const blocks: string[] = [];
    const advisories: string[] = [];

    for (const check of this.checks) {
      const result = check.run(context);
      blocks.push(...result.blocks);
      advisories.push(...result.advisories);
    }

    return {
      shouldStop: blocks.length === 0,
      reason: blocks.length > 0 ? blocks[0] : "All checks passed",
      blocks,
      advisories,
    };
  }
}

export interface StopGateContext {
  readonly hasSourceWrites: boolean;
  readonly hasTests: boolean;
  readonly hasVerification: boolean;
  readonly changedFiles: readonly string[];
  readonly recentFailures: number;
}

export interface StopCheckResult {
  readonly blocks: readonly string[];
  readonly advisories: readonly string[];
}

export interface StopCheck {
  readonly name: string;
  run(context: StopGateContext): StopCheckResult;
}

export class VerificationCheck implements StopCheck {
  readonly name = "verification";

  run(context: StopGateContext): StopCheckResult {
    if (context.hasSourceWrites && !context.hasVerification) {
      return {
        blocks: ["Code was modified but NO verification commands were run."],
        advisories: [],
      };
    }
    return { blocks: [], advisories: [] };
  }
}

export class RecentFailuresCheck implements StopCheck {
  readonly name = "recent-failures";

  run(context: StopGateContext): StopCheckResult {
    if (context.recentFailures >= 3) {
      return {
        blocks: [
          `Last ${context.recentFailures} commands ALL FAILED. ` +
          "Do not claim completion with unresolved failures.",
        ],
        advisories: [],
      };
    }
    return { blocks: [], advisories: [] };
  }
}

function extractHintFromRecord(data: Record<string, unknown>): LeaderHint | null {
  const raw = data["LEADER_HINT"];
  if (!isRecord(raw)) return null;
  const intents = raw["detected_intents"];
  if (!Array.isArray(intents)) return null;

  const parsed: IntentEntry[] = [];
  for (const item of intents) {
    if (isRecord(item) && typeof item["intent"] === "string") {
      parsed.push({
        intent: item["intent"],
        confidence: typeof item["confidence"] === "number" ? item["confidence"] : 0,
      });
    }
  }
  return parsed.length > 0 ? { detectedIntents: parsed } : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
