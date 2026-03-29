import type { PolicyDecision } from "./policy.js";

export interface MiddlewareContext {
  readonly toolName: string;
  readonly toolArgs: Readonly<Record<string, unknown>>;
  readonly sessionId?: string;
  readonly requestId: string;
  readonly timestamp: string;
  response?: unknown;
}

export interface MiddlewareResult {
  readonly decision: "allow" | "deny" | "continue";
  readonly reason?: string;
  readonly response?: unknown;
  readonly policyDecision?: PolicyDecision;
}

export type MiddlewareFn = (
  ctx: MiddlewareContext,
  next: () => Promise<unknown>
) => Promise<MiddlewareResult | unknown>;

export interface ToolRegistration {
  readonly name: string;
  readonly description: string;
  readonly inputSchema: Readonly<Record<string, unknown>>;
  readonly handler: (args: Readonly<Record<string, unknown>>) => Promise<unknown>;
  readonly middleware?: readonly MiddlewareFn[];
}
