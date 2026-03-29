import type { HookContext, HookResult } from "../interfaces/hooks.js";
import { resolve, join } from "node:path";
import { existsSync, mkdirSync } from "node:fs";

const PERFORMANCE_BUDGET_MS = 100;

const BYPASS_MODES = new Set(["bypasspermissions", "dontask"]);

export interface ReentryGuardOptions {
  readonly waitMs?: number;
}

export class HookReentryGuard {
  private readonly active = new Map<string, Promise<void>>();
  private readonly resolvers = new Map<string, () => void>();

  async acquire(
    hookName: string,
    options: ReentryGuardOptions = {},
  ): Promise<() => Promise<void>> {
    if (this.active.has(hookName)) {
      if ((options.waitMs ?? -1) === 0) {
        throw new Error(`Reentrant hook execution blocked: ${hookName}`);
      }
      await this.active.get(hookName);
    }

    let resolver!: () => void;
    const promise = new Promise<void>((res) => {
      resolver = res;
    });
    this.active.set(hookName, promise);
    this.resolvers.set(hookName, resolver);

    return async () => {
      this.active.delete(hookName);
      const res = this.resolvers.get(hookName);
      this.resolvers.delete(hookName);
      res?.();
    };
  }
}

export function setupCrashHandler(
  hookName: string,
  failClosed: boolean,
): (ctx: HookContext, fn: () => Promise<HookResult>) => Promise<HookResult> {
  return async (
    _ctx: HookContext,
    fn: () => Promise<HookResult>,
  ): Promise<HookResult> => {
    try {
      return await fn();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (failClosed) {
        return denyDecision(
          `Hook '${hookName}' crashed (fail-closed): ${message}`,
        );
      }
      return allowDecision(
        `Hook '${hookName}' crashed (fail-open): ${message}`,
      );
    }
  };
}

export function denyDecision(reason: string): HookResult {
  return {
    decision: {
      action: "deny",
      reason,
      riskLevel: "high",
      tags: ["hook-crash"],
    },
  };
}

export function blockDecision(reason: string): HookResult {
  return {
    decision: {
      action: "block",
      reason,
      riskLevel: "critical",
      tags: ["hook-block"],
    },
  };
}

export function allowDecision(reason: string): HookResult {
  return {
    decision: {
      action: "allow",
      reason,
      riskLevel: "low",
      tags: [],
    },
  };
}

export function isBypassMode(data: Record<string, unknown>): boolean {
  if (data["bypass"] === true) return true;
  const mode = String(data["permission_mode"] ?? "")
    .toLowerCase()
    .trim();
  return BYPASS_MODES.has(mode);
}

export function bootstrapRuntimePaths(anchor: string): {
  projectDir: string;
  stateDir: string;
  omgDir: string;
} {
  const projectDir = resolve(anchor);
  const omgDir = join(projectDir, ".omg");
  const stateDir = join(omgDir, "state");
  if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true });
  return { projectDir, stateDir, omgDir };
}

export function checkPerformanceBudget(
  startMs: number,
  hookName: string,
): boolean {
  const elapsed = Date.now() - startMs;
  if (elapsed > PERFORMANCE_BUDGET_MS) {
    console.warn(
      `[OMG] Hook '${hookName}' exceeded ${PERFORMANCE_BUDGET_MS}ms budget: ${elapsed}ms`,
    );
    return false;
  }
  return true;
}
