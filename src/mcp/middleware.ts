import { randomUUID } from "node:crypto";
import type { MiddlewareContext, MiddlewareFn, MiddlewareResult } from "./types.js";

export class MiddlewareStack {
  private readonly middlewares: MiddlewareFn[] = [];

  use(fn: MiddlewareFn): this {
    this.middlewares.push(fn);
    return this;
  }

  before(fn: (ctx: MiddlewareContext) => Promise<MiddlewareResult | void>): this {
    return this.use(async (ctx, next) => {
      const result = await fn(ctx);
      if (result && isMiddlewareResult(result) && result.decision === "deny") {
        return result;
      }
      return next();
    });
  }

  after(fn: (ctx: MiddlewareContext, result: unknown) => Promise<unknown>): this {
    return this.use(async (ctx, next) => {
      const result = await next();
      return fn(ctx, result);
    });
  }

  async execute(ctx: MiddlewareContext, terminal: () => Promise<unknown>): Promise<unknown> {
    const stack = [...this.middlewares];
    let index = 0;

    const dispatch = async (): Promise<unknown> => {
      if (index >= stack.length) {
        return terminal();
      }

      const middleware = stack[index++];
      if (!middleware) {
        return terminal();
      }

      try {
        const result = await middleware(ctx, dispatch);
        if (isMiddlewareResult(result) && result.decision === "deny") {
          return {
            decision: "deny",
            reason: result.reason ?? "Denied by middleware",
            response: result.response,
          };
        }
        return result;
      } catch (error) {
        return {
          decision: "deny",
          reason: `Middleware error: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
    };

    return dispatch();
  }

  get size(): number {
    return this.middlewares.length;
  }

  static createContext(
    toolName: string,
    toolArgs: Record<string, unknown>,
    projectDir: string,
    sessionId?: string,
  ): MiddlewareContext {
    return {
      toolName,
      toolArgs: Object.freeze({ ...toolArgs }),
      ...(sessionId ? { sessionId } : {}),
      requestId: randomUUID(),
      timestamp: new Date().toISOString(),
      projectDir,
    };
  }
}

function isMiddlewareResult(value: unknown): value is MiddlewareResult {
  return (
    typeof value === "object" &&
    value !== null &&
    "decision" in value &&
    typeof (value as MiddlewareResult).decision === "string"
  );
}

export { isMiddlewareResult };
