import {
  HookReentryGuard,
  allowDecision,
  setupCrashHandler,
} from "./common.js";
import {
  getHookRegistrations,
  type ResolvedSettings,
} from "../config/settings.js";
import type { Settings } from "../types/config.js";
import type { HookContext, HookFn, HookResult } from "../interfaces/hooks.js";

export type HookLifecyclePhase =
  | "session-start"
  | "session-end"
  | "pre-tool"
  | "post-tool"
  | "stop-gate";

export type HookLifecycleContext = Omit<HookContext, "phase">;

interface RegisteredHook {
  readonly phase: HookLifecyclePhase;
  readonly name: string;
  readonly priority: number;
  readonly order: number;
  readonly handler: HookFn;
}

export interface HookLifecycleManagerOptions {
  readonly reentryGuard?: HookReentryGuard;
  readonly hookRegistrations?: Readonly<Record<string, readonly string[]>>;
  readonly failClosedPhases?: Partial<Record<HookLifecyclePhase, boolean>>;
}

const DEFAULT_FAIL_CLOSED_PHASES: Readonly<Record<HookLifecyclePhase, boolean>> = {
  "session-start": false,
  "session-end": false,
  "pre-tool": true,
  "post-tool": false,
  "stop-gate": true,
};

const PHASE_NAME_MAP: Readonly<Record<HookLifecyclePhase, HookContext["phase"]>> = {
  "session-start": "session_start",
  "session-end": "session_end",
  "pre-tool": "pre_tool",
  "post-tool": "post_tool",
  "stop-gate": "stop",
};

export class HookLifecycleManager {
  static create(
    settings?: Settings | ResolvedSettings,
    options: Omit<HookLifecycleManagerOptions, "hookRegistrations"> = {},
  ): HookLifecycleManager {
    if (settings === undefined) {
      return new HookLifecycleManager(options);
    }

    const rawSettings = isResolvedSettings(settings) ? settings.raw : settings;
    return new HookLifecycleManager({
      ...options,
      hookRegistrations: getHookRegistrations(rawSettings),
    });
  }

  private readonly hooks = new Map<HookLifecyclePhase, RegisteredHook[]>();
  private readonly reentryGuard: HookReentryGuard;
  private readonly failClosedByPhase: Readonly<Record<HookLifecyclePhase, boolean>>;
  private readonly settingsOrderByPhase = new Map<
    HookLifecyclePhase,
    ReadonlyMap<string, number>
  >();
  private nextOrder = 0;

  constructor(options: HookLifecycleManagerOptions = {}) {
    this.reentryGuard = options.reentryGuard ?? new HookReentryGuard();
    this.failClosedByPhase = {
      ...DEFAULT_FAIL_CLOSED_PHASES,
      ...options.failClosedPhases,
    };
    this.seedPhaseOrdering(options.hookRegistrations);
  }

  registerHook(
    phase: HookLifecyclePhase,
    handler: HookFn,
    priority?: number,
  ): void {
    const hooksForPhase = this.hooks.get(phase) ?? [];
    const order = this.nextOrder;
    this.nextOrder += 1;
    const hookName = getHookName(handler, phase, order);
    const effectivePriority =
      priority ?? this.resolveSettingsPriority(phase, hookName, order);
    const failClosed = this.failClosedByPhase[phase];
    const crashHandler = setupCrashHandler(hookName, failClosed);

    const wrapped: HookFn = async (ctx) =>
      crashHandler(ctx, async () => Promise.resolve(handler(ctx)));

    hooksForPhase.push({
      phase,
      name: hookName,
      priority: effectivePriority,
      order,
      handler: wrapped,
    });

    hooksForPhase.sort((left, right) => {
      if (left.priority !== right.priority) return left.priority - right.priority;
      return left.order - right.order;
    });

    this.hooks.set(phase, hooksForPhase);
  }

  async runSessionStart(context: HookLifecycleContext): Promise<HookResult[]> {
    return this.runPhase("session-start", context);
  }

  async runSessionEnd(context: HookLifecycleContext): Promise<HookResult[]> {
    return this.runPhase("session-end", context);
  }

  async runPreTool(context: HookLifecycleContext): Promise<HookResult> {
    const hooksForPhase = this.hooks.get("pre-tool") ?? [];
    if (hooksForPhase.length === 0) {
      return allowDecision("No pre-tool hooks registered.");
    }

    const release = await this.reentryGuard.acquire("hook-lifecycle:pre-tool");
    try {
      const hookContext = buildHookContext("pre-tool", context);
      for (const hook of hooksForPhase) {
        const result = await hook.handler(hookContext);
        if (result.decision.action === "deny" || result.decision.action === "block") {
          return result;
        }
      }
      return allowDecision("All pre-tool hooks allowed execution.");
    } finally {
      await release();
    }
  }

  async runPostTool(
    context: HookLifecycleContext,
    result: unknown,
  ): Promise<HookResult[]> {
    return this.runPhase("post-tool", context, toToolOutput(result));
  }

  async runStopGate(context: HookLifecycleContext): Promise<HookResult[]> {
    return this.runPhase("stop-gate", context);
  }

  private async runPhase(
    phase: HookLifecyclePhase,
    context: HookLifecycleContext,
    toolOutput?: Readonly<Record<string, unknown>>,
  ): Promise<HookResult[]> {
    const hooksForPhase = this.hooks.get(phase) ?? [];
    if (hooksForPhase.length === 0) return [];

    const release = await this.reentryGuard.acquire(`hook-lifecycle:${phase}`);
    try {
      const hookContext = buildHookContext(phase, context, toolOutput);
      const results: HookResult[] = [];
      for (const hook of hooksForPhase) {
        const result = await hook.handler(hookContext);
        results.push(result);
      }
      return results;
    } finally {
      await release();
    }
  }

  private seedPhaseOrdering(
    registrations?: Readonly<Record<string, readonly string[]>>,
  ): void {
    if (registrations === undefined) return;
    for (const [phaseName, hookNames] of Object.entries(registrations)) {
      const phase = normalizePhase(phaseName);
      if (phase === undefined) continue;
      const mapping = new Map<string, number>();
      for (let index = 0; index < hookNames.length; index += 1) {
        const hookName = hookNames[index];
        mapping.set(hookName, index);
      }
      this.settingsOrderByPhase.set(phase, mapping);
    }
  }

  private resolveSettingsPriority(
    phase: HookLifecyclePhase,
    hookName: string,
    registrationOrder: number,
  ): number {
    const orderMap = this.settingsOrderByPhase.get(phase);
    const configuredOrder = orderMap?.get(hookName);
    if (configuredOrder !== undefined) return configuredOrder;
    return 1000 + registrationOrder;
  }
}

function getHookName(fn: HookFn, phase: HookLifecyclePhase, order: number): string {
  const name = fn.name.trim();
  if (name.length > 0) return name;
  return `${phase}-hook-${order}`;
}

function buildHookContext(
  phase: HookLifecyclePhase,
  context: HookLifecycleContext,
  toolOutput?: Readonly<Record<string, unknown>>,
): HookContext {
  return {
    ...context,
    phase: PHASE_NAME_MAP[phase],
    ...(toolOutput === undefined ? {} : { toolOutput }),
  };
}

function toToolOutput(value: unknown): Readonly<Record<string, unknown>> | undefined {
  if (value === null || value === undefined) return undefined;
  if (!isRecord(value)) {
    return { result: value };
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isResolvedSettings(value: Settings | ResolvedSettings): value is ResolvedSettings {
  return "raw" in value;
}

function normalizePhase(raw: string): HookLifecyclePhase | undefined {
  const normalized = raw.trim().toLowerCase().replace(/[_\s]+/g, "-");
  switch (normalized) {
    case "sessionstart":
    case "session-start":
      return "session-start";
    case "sessionend":
    case "session-end":
      return "session-end";
    case "pretool":
    case "pre-tool":
    case "pre-tool-use":
      return "pre-tool";
    case "posttool":
    case "post-tool":
    case "post-tool-use":
    case "post-tool-use-failure":
      return "post-tool";
    case "stop":
    case "stop-gate":
      return "stop-gate";
    default:
      return undefined;
  }
}
