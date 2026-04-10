// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TokenEntry {
  readonly id: string;
  readonly tokens: number;
  readonly timestamp: number;
}

export interface WastePattern {
  readonly type: "repeated_error" | "duplicate_research" | "context_rebuild";
  readonly description: string;
  readonly wastedTokens: number;
  readonly occurrences: number;
}

export interface EfficiencyReport {
  readonly sessionTokens: ReadonlyMap<string, number>;
  readonly taskTokens: ReadonlyMap<string, number>;
  readonly wastedTokens: number;
  readonly savings: number;
  readonly recommendations: readonly string[];
  readonly wastePatterns: readonly WastePattern[];
  readonly totalTokens: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REPEATED_ERROR_THRESHOLD = 3;
const DUPLICATE_RESEARCH_THRESHOLD = 2;
const CONTEXT_REBUILD_TOKEN_THRESHOLD = 10_000;
const CONTEXT_REBUILD_COUNT_THRESHOLD = 3;

// ---------------------------------------------------------------------------
// TokenBudget
// ---------------------------------------------------------------------------

export class TokenBudget {
  private readonly sessions: Map<string, number> = new Map();
  private readonly tasks: Map<string, number> = new Map();
  private readonly sessionEntries: Map<string, TokenEntry[]> = new Map();
  private readonly taskEntries: Map<string, TokenEntry[]> = new Map();

  trackSessionTokens(sessionId: string, tokens: number): void {
    const current = this.sessions.get(sessionId) ?? 0;
    this.sessions.set(sessionId, current + tokens);

    const entries = this.sessionEntries.get(sessionId) ?? [];
    entries.push({ id: sessionId, tokens, timestamp: Date.now() });
    this.sessionEntries.set(sessionId, entries);
  }

  trackTaskTokens(taskId: string, tokens: number): void {
    const current = this.tasks.get(taskId) ?? 0;
    this.tasks.set(taskId, current + tokens);

    const entries = this.taskEntries.get(taskId) ?? [];
    entries.push({ id: taskId, tokens, timestamp: Date.now() });
    this.taskEntries.set(taskId, entries);
  }

  getSessionTokens(sessionId: string): number {
    return this.sessions.get(sessionId) ?? 0;
  }

  getTaskTokens(taskId: string): number {
    return this.tasks.get(taskId) ?? 0;
  }

  getTotalTokens(): number {
    let total = 0;
    for (const v of this.tasks.values()) {
      total += v;
    }
    return total;
  }

  getReport(): EfficiencyReport {
    const wastePatterns = this.detectWastePatterns();
    const wastedTokens = wastePatterns.reduce(
      (sum, p) => sum + p.wastedTokens,
      0,
    );
    const totalTokens = this.getTotalTokens();
    const savings = totalTokens > 0 ? wastedTokens / totalTokens : 0;
    const recommendations = this.buildRecommendations(wastePatterns);

    return {
      sessionTokens: new Map(this.sessions),
      taskTokens: new Map(this.tasks),
      wastedTokens,
      savings,
      recommendations,
      wastePatterns,
      totalTokens,
    };
  }

  // -------------------------------------------------------------------------
  // Waste detection (script-based, no LLM)
  // -------------------------------------------------------------------------

  private detectWastePatterns(): WastePattern[] {
    const patterns: WastePattern[] = [];
    patterns.push(...this.detectRepeatedErrors());
    patterns.push(...this.detectDuplicateResearch());
    patterns.push(...this.detectContextRebuilds());
    return patterns;
  }

  private detectRepeatedErrors(): WastePattern[] {
    const patterns: WastePattern[] = [];

    for (const [taskId, entries] of this.taskEntries) {
      if (entries.length >= REPEATED_ERROR_THRESHOLD) {
        const sorted = [...entries].sort((a, b) => a.timestamp - b.timestamp);
        // Burst detection: identical-size calls indicate error retries
        const sizeCounts = new Map<number, number>();
        for (const entry of sorted) {
          const count = sizeCounts.get(entry.tokens) ?? 0;
          sizeCounts.set(entry.tokens, count + 1);
        }

        for (const [tokenSize, count] of sizeCounts) {
          if (count >= REPEATED_ERROR_THRESHOLD) {
            patterns.push({
              type: "repeated_error",
              description: `Task "${taskId}" had ${count} calls of ${tokenSize} tokens each (likely retries)`,
              wastedTokens: tokenSize * (count - 1),
              occurrences: count,
            });
          }
        }
      }
    }

    return patterns;
  }

  private detectDuplicateResearch(): WastePattern[] {
    const patterns: WastePattern[] = [];
    const taskIds = [...this.tasks.keys()];

    const tokenCounts = new Map<number, string[]>();
    for (const id of taskIds) {
      const tokens = this.tasks.get(id) ?? 0;
      const ids = tokenCounts.get(tokens) ?? [];
      ids.push(id);
      tokenCounts.set(tokens, ids);
    }

    for (const [tokens, ids] of tokenCounts) {
      if (ids.length >= DUPLICATE_RESEARCH_THRESHOLD && tokens > 0) {
        patterns.push({
          type: "duplicate_research",
          description: `${ids.length} tasks consumed exactly ${tokens} tokens each: ${ids.join(", ")}`,
          wastedTokens: tokens * (ids.length - 1),
          occurrences: ids.length,
        });
      }
    }

    return patterns;
  }

  private detectContextRebuilds(): WastePattern[] {
    const patterns: WastePattern[] = [];

    for (const [sessionId, entries] of this.sessionEntries) {
      const largeEntries = entries.filter(
        (e) => e.tokens >= CONTEXT_REBUILD_TOKEN_THRESHOLD,
      );
      if (largeEntries.length >= CONTEXT_REBUILD_COUNT_THRESHOLD) {
        const wastedTokens = largeEntries
          .slice(1)
          .reduce((sum, e) => sum + e.tokens, 0);
        patterns.push({
          type: "context_rebuild",
          description: `Session "${sessionId}" had ${largeEntries.length} large token bursts (>=${CONTEXT_REBUILD_TOKEN_THRESHOLD} tokens), suggesting context rebuilds`,
          wastedTokens,
          occurrences: largeEntries.length,
        });
      }
    }

    return patterns;
  }

  private buildRecommendations(patterns: readonly WastePattern[]): string[] {
    const recs: string[] = [];
    const types = new Set(patterns.map((p) => p.type));

    if (types.has("repeated_error")) {
      recs.push("Fix root cause of repeated errors to avoid retry token waste");
    }
    if (types.has("duplicate_research")) {
      recs.push("Cache research results to avoid duplicate exploration costs");
    }
    if (types.has("context_rebuild")) {
      recs.push("Use session checkpoints to avoid expensive context rebuilds");
    }
    if (patterns.length === 0) {
      recs.push("No waste patterns detected — token usage looks efficient");
    }

    return recs;
  }
}
