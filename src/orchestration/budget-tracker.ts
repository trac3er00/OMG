import { BudgetEnvelope, type BudgetLimits } from "./budget.js";

export const DEFAULT_BUDGET: BudgetLimits = {
  tokens: 500_000,
  wall_time_ms: 600_000,
  memory_mb: 2048,
};

export class BudgetTracker {
  private readonly budget: BudgetEnvelope;

  constructor(sessionId: string, limits: BudgetLimits = DEFAULT_BUDGET) {
    this.budget = BudgetEnvelope.create(sessionId, limits);
  }

  check() {
    return this.budget.check();
  }

  recordWallTime(ms: number): void {
    this.budget.record("wall_time_ms", ms);
  }

  pressureSnapshot(): Readonly<Record<string, number>> {
    return {
      tokens: this.budget.pressure("tokens"),
      wall_time_ms: this.budget.pressure("wall_time_ms"),
      memory_mb: this.budget.pressure("memory_mb"),
    };
  }

  toSnapshot() {
    return this.budget.toSnapshot();
  }
}

export type { BudgetLimits };
