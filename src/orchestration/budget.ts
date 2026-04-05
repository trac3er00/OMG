// Ported from runtime/budget_envelopes.py

import type { BudgetEnvelope as BudgetEnvelopeSnapshot } from "../interfaces/orchestration.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type BudgetDimension =
  | "tokens"
  | "cpu_ms"
  | "memory_mb"
  | "wall_time_ms"
  | "network_bytes";

export interface BudgetCheckResult {
  readonly exceeded: boolean;
  readonly dimensions: readonly string[];
}

export interface BudgetLimits {
  readonly tokens?: number;
  readonly cpu_ms?: number;
  readonly memory_mb?: number;
  readonly wall_time_ms?: number;
  readonly network_bytes?: number;
}

// ---------------------------------------------------------------------------
// Dimension metadata
// ---------------------------------------------------------------------------

const ALL_DIMENSIONS: readonly BudgetDimension[] = [
  "tokens",
  "cpu_ms",
  "memory_mb",
  "wall_time_ms",
  "network_bytes",
] as const;

// ---------------------------------------------------------------------------
// BudgetEnvelope class
// ---------------------------------------------------------------------------

export class BudgetEnvelope {
  readonly runId: string;
  private readonly limits: ReadonlyMap<BudgetDimension, number>;
  private readonly usage: Map<BudgetDimension, number>;

  private constructor(runId: string, limits: Map<BudgetDimension, number>) {
    this.runId = runId;
    this.limits = limits;
    this.usage = new Map<BudgetDimension, number>();
    for (const dim of ALL_DIMENSIONS) {
      this.usage.set(dim, 0);
    }
  }

  static create(runId: string, limits: BudgetLimits): BudgetEnvelope {
    const limitsMap = new Map<BudgetDimension, number>();
    for (const dim of ALL_DIMENSIONS) {
      const val = limits[dim];
      if (val !== undefined && val > 0) {
        limitsMap.set(dim, val);
      }
    }
    return new BudgetEnvelope(runId, limitsMap);
  }

  record(dimension: BudgetDimension, amount: number): void {
    const current = this.usage.get(dimension) ?? 0;
    if (dimension === "memory_mb") {
      this.usage.set(dimension, Math.max(current, amount));
    } else {
      this.usage.set(dimension, current + amount);
    }
  }

  check(): BudgetCheckResult {
    const exceededDims: string[] = [];
    for (const [dim, limit] of this.limits) {
      const used = this.usage.get(dim) ?? 0;
      if (used >= limit) {
        exceededDims.push(dim);
      }
    }
    return { exceeded: exceededDims.length > 0, dimensions: exceededDims };
  }

  remaining(dimension: BudgetDimension): number {
    const limit = this.limits.get(dimension);
    if (limit === undefined) {
      return Infinity;
    }
    const used = this.usage.get(dimension) ?? 0;
    return Math.max(0, limit - used);
  }

  used(dimension: BudgetDimension): number {
    return this.usage.get(dimension) ?? 0;
  }

  pressure(dimension: BudgetDimension): number {
    const limit = this.limits.get(dimension);
    if (limit === undefined || limit <= 0) {
      return 0;
    }
    const usedVal = this.usage.get(dimension) ?? 0;
    return usedVal / limit;
  }

  toSnapshot(): BudgetEnvelopeSnapshot {
    const checkResult = this.check();

    const limitFor = (dim: BudgetDimension): number =>
      this.limits.get(dim) ?? 0;
    const usedFor = (dim: BudgetDimension): number =>
      this.usage.get(dim) ?? 0;

    return {
      runId: this.runId,
      cpuSecondsLimit: limitFor("cpu_ms"),
      memoryMbLimit: limitFor("memory_mb"),
      wallTimeSecondsLimit: limitFor("wall_time_ms"),
      tokenLimit: limitFor("tokens"),
      networkBytesLimit: limitFor("network_bytes"),
      cpuSecondsUsed: usedFor("cpu_ms"),
      memoryMbPeak: usedFor("memory_mb"),
      wallTimeSecondsUsed: usedFor("wall_time_ms"),
      tokensUsed: usedFor("tokens"),
      networkBytesUsed: usedFor("network_bytes"),
      exceeded: checkResult.exceeded,
      exceededDimensions: checkResult.dimensions,
    };
  }
}
