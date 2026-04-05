import type { PolicyDecision } from "./policy.js";

export type HookPhase = "session_start" | "session_end" | "pre_tool" | "post_tool" | "stop";

export interface HookContext {
  readonly phase: HookPhase;
  readonly toolName?: string;
  readonly toolInput?: Readonly<Record<string, unknown>>;
  readonly toolOutput?: Readonly<Record<string, unknown>>;
  readonly sessionId?: string;
  readonly projectDir: string;
  readonly timestamp: string;
}

export interface HookResult {
  readonly decision: PolicyDecision;
  readonly modified?: boolean;
  readonly evidence?: Readonly<Record<string, unknown>>;
}

export type HookFn = (ctx: HookContext) => Promise<HookResult> | HookResult;

export interface HookRegistration {
  readonly name: string;
  readonly phase: HookPhase;
  readonly priority: number;
  readonly failClosed: boolean;
  readonly fn: HookFn;
}
