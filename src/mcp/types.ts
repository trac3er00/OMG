/**
 * MCP middleware type definitions.
 * Middleware enables Express.js-style request interception for every tool call.
 */

export interface MiddlewareContext {
  /** The MCP tool name being called */
  readonly toolName: string;
  /** The tool's input arguments */
  readonly toolArgs: Readonly<Record<string, unknown>>;
  /** Session identifier (from MCP initialize params) */
  readonly sessionId?: string;
  /** Unique request ID for tracing */
  readonly requestId: string;
  /** ISO timestamp of the request */
  readonly timestamp: string;
  /** Project directory for state resolution */
  readonly projectDir: string;
  /** Mutable response slot — middleware can set this to short-circuit */
  response?: unknown;
}

export type MiddlewareDecision = "allow" | "deny" | "continue";

export interface MiddlewareResult {
  readonly decision: MiddlewareDecision;
  readonly reason?: string;
  /** If set, this becomes the tool's response (bypasses tool execution) */
  readonly response?: unknown;
}

/**
 * A middleware function. Return MiddlewareResult to short-circuit.
 * Call next() to continue to the next middleware or the tool itself.
 */
export type MiddlewareFn = (
  ctx: MiddlewareContext,
  next: () => Promise<unknown>
) => Promise<MiddlewareResult | unknown>;

export interface ToolHandler<TArgs = Record<string, unknown>, TResult = unknown> {
  (args: TArgs): Promise<TResult>;
}
