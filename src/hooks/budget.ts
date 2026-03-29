export const BudgetConstants = {
  SESSION_TOTAL: 2000,
  SESSION_IDLE: 200,
  PROFILE: 200,
  WORKING_MEMORY: 400,
  HANDOFF: 300,
  MEMORY: 300,
  FAILURES: 200,
  TOOLS: 100,
  PLANNING: 100,
  RALPH: 100,

  PROMPT_TOTAL: 1000,
  INTENT_DISCIPLINE: 200,
  KNOWLEDGE: 300,
  LEARNINGS: 200,
  AGENT_ROUTING: 200,
  MODE: 100,
} as const;

export interface CostEntry {
  readonly ts: string;
  readonly tool: string;
  readonly tokensIn: number;
  readonly tokensOut: number;
  readonly costUsd: number;
  readonly model: string;
  readonly sessionId: string;
}

export interface CostSummary {
  readonly totalTokens: number;
  readonly totalCostUsd: number;
  readonly byTool: Readonly<Record<string, ToolCostAggregate>>;
  readonly bySession: Readonly<Record<string, SessionCostAggregate>>;
  readonly entryCount: number;
}

export interface ToolCostAggregate {
  readonly tokens: number;
  readonly costUsd: number;
  readonly count: number;
}

export interface SessionCostAggregate {
  readonly tokens: number;
  readonly costUsd: number;
  readonly count: number;
}

export interface CostLedgerDeps {
  readonly readLines: (path: string) => Promise<readonly string[]>;
  readonly appendLine: (path: string, line: string) => Promise<void>;
  readonly fileSize: (path: string) => Promise<number>;
  readonly rename: (src: string, dest: string) => Promise<void>;
  readonly remove: (path: string) => Promise<void>;
  readonly exists: (path: string) => Promise<boolean>;
  readonly mkdirp: (dir: string) => Promise<void>;
}

const MAX_LEDGER_BYTES = 5 * 1024 * 1024;

export class CostLedger {
  private readonly deps: CostLedgerDeps;
  private readonly ledgerDir: string;
  private readonly ledgerPath: string;

  constructor(projectDir: string, deps: CostLedgerDeps) {
    this.deps = deps;
    this.ledgerDir = `${projectDir}/.omg/state/ledger`;
    this.ledgerPath = `${this.ledgerDir}/cost-ledger.jsonl`;
  }

  async appendEntry(entry: CostEntry): Promise<void> {
    await this.deps.mkdirp(this.ledgerDir);
    const line = JSON.stringify({
      ts: entry.ts,
      tool: entry.tool,
      tokens_in: entry.tokensIn,
      tokens_out: entry.tokensOut,
      cost_usd: entry.costUsd,
      model: entry.model,
      session_id: entry.sessionId,
    });
    await this.deps.appendLine(this.ledgerPath, line + "\n");
  }

  async readSummary(): Promise<CostSummary> {
    const empty: CostSummary = {
      totalTokens: 0,
      totalCostUsd: 0,
      byTool: {},
      bySession: {},
      entryCount: 0,
    };

    const exists = await this.deps.exists(this.ledgerPath);
    if (!exists) return empty;

    const lines = await this.deps.readLines(this.ledgerPath);

    let totalTokens = 0;
    let totalCostUsd = 0;
    const byTool: Record<string, { tokens: number; costUsd: number; count: number }> = {};
    const bySession: Record<string, { tokens: number; costUsd: number; count: number }> = {};
    let entryCount = 0;

    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;

      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(line) as Record<string, unknown>;
      } catch {
        continue;
      }

      const tokensIn = safeInt(parsed["tokens_in"]);
      const tokensOut = safeInt(parsed["tokens_out"]);
      const costUsd = safeFloat(parsed["cost_usd"]);
      const tool = String(parsed["tool"] ?? "unknown");
      const sessionId = String(parsed["session_id"] ?? "unknown");
      const lineTokens = tokensIn + tokensOut;

      totalTokens += lineTokens;
      totalCostUsd += costUsd;
      entryCount += 1;

      if (byTool[tool] === undefined) {
        byTool[tool] = { tokens: 0, costUsd: 0, count: 0 };
      }
      byTool[tool].tokens += lineTokens;
      byTool[tool].costUsd += costUsd;
      byTool[tool].count += 1;

      if (bySession[sessionId] === undefined) {
        bySession[sessionId] = { tokens: 0, costUsd: 0, count: 0 };
      }
      bySession[sessionId].tokens += lineTokens;
      bySession[sessionId].costUsd += costUsd;
      bySession[sessionId].count += 1;
    }

    return { totalTokens, totalCostUsd, byTool, bySession, entryCount };
  }

  async rotate(): Promise<void> {
    const exists = await this.deps.exists(this.ledgerPath);
    if (!exists) return;

    const size = await this.deps.fileSize(this.ledgerPath);
    if (size <= MAX_LEDGER_BYTES) return;

    const archive = this.ledgerPath + ".1";
    const archiveExists = await this.deps.exists(archive);
    if (archiveExists) {
      await this.deps.remove(archive);
    }
    await this.deps.rename(this.ledgerPath, archive);
  }
}

export interface BudgetConfig {
  readonly sessionLimitUsd: number;
  readonly inputPerMtok: number;
  readonly outputPerMtok: number;
}

export interface BudgetUsage {
  readonly usedCostUsd: number;
  readonly usedCalls: number;
  readonly sessionLimitUsd: number;
  readonly projectedCalls: number;
}

export interface BudgetCheckResult {
  readonly exceeded: boolean;
  readonly remaining: number;
  readonly remainingPct: number;
  readonly context: string;
  readonly thresholdAlerts: readonly string[];
}

const DEFAULT_SESSION_LIMIT_USD = 5.0;
const DEFAULT_INPUT_PER_MTOK = 3.0;
const DEFAULT_OUTPUT_PER_MTOK = 15.0;
const DEFAULT_PROJECTED_TOOL_CALLS = 50;
const DEFAULT_THRESHOLDS: readonly number[] = [50, 80, 95];

export class BudgetGovernor {
  private readonly config: BudgetConfig;
  private readonly thresholds: readonly number[];
  private readonly firedThresholds = new Set<number>();

  constructor(
    config?: Partial<BudgetConfig>,
    thresholds?: readonly number[],
  ) {
    this.config = {
      sessionLimitUsd: config?.sessionLimitUsd ?? DEFAULT_SESSION_LIMIT_USD,
      inputPerMtok: config?.inputPerMtok ?? DEFAULT_INPUT_PER_MTOK,
      outputPerMtok: config?.outputPerMtok ?? DEFAULT_OUTPUT_PER_MTOK,
    };
    this.thresholds = thresholds ?? DEFAULT_THRESHOLDS;
  }

  recordUsage(_tokens: number, cost: number): BudgetUsage {
    return {
      usedCostUsd: cost,
      usedCalls: 1,
      sessionLimitUsd: this.config.sessionLimitUsd,
      projectedCalls: DEFAULT_PROJECTED_TOOL_CALLS,
    };
  }

  getUsage(usedCostUsd: number, usedCalls: number): BudgetUsage {
    const projectedCalls = projectTotalCalls(
      usedCostUsd,
      usedCalls,
      this.config.sessionLimitUsd,
    );
    return {
      usedCostUsd,
      usedCalls,
      sessionLimitUsd: this.config.sessionLimitUsd,
      projectedCalls,
    };
  }

  checkBudget(usedCostUsd: number, usedCalls: number): BudgetCheckResult {
    const sessionLimit = this.config.sessionLimitUsd;
    const remainingRatio = sessionLimit > 0
      ? 1.0 - usedCostUsd / sessionLimit
      : 1.0;
    const remainingPct = Math.round(
      Math.max(0.0, Math.min(1.0, remainingRatio)) * 100,
    );
    const projectedCalls = projectTotalCalls(
      usedCostUsd,
      usedCalls,
      sessionLimit,
    );

    const context = buildBudgetContext(
      usedCostUsd,
      sessionLimit,
      usedCalls,
      projectedCalls,
    );

    const usedPct = sessionLimit > 0
      ? (usedCostUsd / sessionLimit) * 100
      : 0;

    const alerts: string[] = [];
    for (const threshold of this.thresholds) {
      if (usedPct >= threshold && !this.firedThresholds.has(threshold)) {
        this.firedThresholds.add(threshold);
        alerts.push(getThresholdMessage(threshold));
      }
    }

    return {
      exceeded: usedCostUsd >= sessionLimit,
      remaining: Math.max(0, sessionLimit - usedCostUsd),
      remainingPct,
      context,
      thresholdAlerts: alerts,
    };
  }

  estimateCallCost(inputText: string, outputText: string): number {
    const tokensIn = estimateTokensTier1(inputText);
    const tokensOut = estimateTokensTier1(outputText);
    const costIn = (tokensIn / 1_000_000) * this.config.inputPerMtok;
    const costOut = (tokensOut / 1_000_000) * this.config.outputPerMtok;
    return Math.max(0, costIn + costOut);
  }
}

function safeInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string") {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function safeFloat(value: unknown, fallback = 0.0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function estimateTokensTier1(text: string): number {
  if (!text) return 0;
  return Math.max(1, Math.trunc(text.length / 3.5));
}

function projectTotalCalls(
  usedCostUsd: number,
  usedCalls: number,
  sessionLimitUsd: number,
): number {
  if (usedCalls <= 0 || usedCostUsd <= 0) return DEFAULT_PROJECTED_TOOL_CALLS;
  const avgCost = usedCostUsd / usedCalls;
  if (avgCost <= 0) return DEFAULT_PROJECTED_TOOL_CALLS;
  const projected = Math.max(usedCalls, Math.round(sessionLimitUsd / avgCost));
  if (projected > DEFAULT_PROJECTED_TOOL_CALLS * 10) {
    return DEFAULT_PROJECTED_TOOL_CALLS;
  }
  const rounded = Math.round(projected / 10) * 10;
  return Math.max(10, rounded);
}

function buildBudgetContext(
  usedCostUsd: number,
  sessionLimitUsd: number,
  usedCalls: number,
  projectedCalls: number,
): string {
  const remainingRatio = 1.0 - usedCostUsd / sessionLimitUsd;
  const remainingPct = Math.round(
    Math.max(0.0, Math.min(1.0, remainingRatio)) * 100,
  );
  return (
    `Budget: ${remainingPct}% remaining | ` +
    `$${usedCostUsd.toFixed(2)} of $${sessionLimitUsd.toFixed(2)} used | ` +
    `${usedCalls} tool calls of ~${projectedCalls}`
  );
}

function getThresholdMessage(pct: number): string {
  if (pct >= 95) {
    return (
      `@cost-limit: ${pct}% budget used. ` +
      "Complete current task and stop. Do NOT start new tasks."
    );
  }
  if (pct >= 80) {
    return (
      `@cost-critical: ${pct}% budget used. ` +
      "Be efficient — minimize unnecessary tool calls, " +
      "batch operations where possible."
    );
  }
  return `@cost-warning: ${pct}% budget used`;
}
