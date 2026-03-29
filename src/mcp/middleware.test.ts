import { describe, test, expect, mock } from "bun:test";
import { MiddlewareStack } from "./middleware.js";
import type { MiddlewareContext } from "./types.js";

function makeCtx(overrides: Partial<MiddlewareContext> = {}): MiddlewareContext {
  return {
    toolName: "test-tool",
    toolArgs: {},
    requestId: "test-req-001",
    timestamp: new Date().toISOString(),
    projectDir: "/tmp/test",
    ...overrides,
  };
}

describe("MiddlewareStack", () => {
  test("empty stack passes through to terminal", async () => {
    const stack = new MiddlewareStack();
    const terminal = mock(async () => ({ result: "ok" }));
    const ctx = makeCtx();

    const result = await stack.execute(ctx, terminal);

    expect(terminal).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ result: "ok" });
  });

  test("single middleware runs and passes through", async () => {
    const stack = new MiddlewareStack();
    const order: string[] = [];

    stack.use(async (_ctx, next) => {
      order.push("middleware-before");
      const result = await next();
      order.push("middleware-after");
      return result;
    });

    const terminal = async () => {
      order.push("terminal");
      return "done";
    };

    const result = await stack.execute(makeCtx(), terminal);

    expect(order).toEqual(["middleware-before", "terminal", "middleware-after"]);
    expect(result).toBe("done");
  });

  test("multiple middlewares run in registration order", async () => {
    const stack = new MiddlewareStack();
    const order: number[] = [];

    stack.use(async (_ctx, next) => {
      order.push(1);
      const r = await next();
      order.push(-1);
      return r;
    });
    stack.use(async (_ctx, next) => {
      order.push(2);
      const r = await next();
      order.push(-2);
      return r;
    });
    stack.use(async (_ctx, next) => {
      order.push(3);
      const r = await next();
      order.push(-3);
      return r;
    });

    await stack.execute(makeCtx(), async () => "done");

    expect(order).toEqual([1, 2, 3, -3, -2, -1]);
  });

  test("deny middleware short-circuits — terminal NOT called", async () => {
    const stack = new MiddlewareStack();
    const terminal = mock(async () => "should-not-be-called");

    stack.use(async () => ({ decision: "deny" as const, reason: "blocked" }));

    const result = await stack.execute(makeCtx(), terminal);

    expect(terminal).not.toHaveBeenCalled();
    expect(result).toMatchObject({ decision: "deny", reason: "blocked" });
  });

  test("error in middleware is caught and returns deny", async () => {
    const stack = new MiddlewareStack();
    const terminal = mock(async () => "ok");

    stack.use(async () => {
      throw new Error("unexpected error");
    });

    const result = await stack.execute(makeCtx(), terminal);

    expect(terminal).not.toHaveBeenCalled();
    expect(result).toMatchObject({ decision: "deny" });
    expect((result as { reason: string }).reason).toContain("unexpected error");
  });

  test("before() helper runs before terminal", async () => {
    const stack = new MiddlewareStack();
    const order: string[] = [];

    stack.before(async () => {
      order.push("before");
    });

    await stack.execute(makeCtx(), async () => {
      order.push("terminal");
      return null;
    });

    expect(order).toEqual(["before", "terminal"]);
  });

  test("before() deny blocks terminal", async () => {
    const stack = new MiddlewareStack();
    const terminal = mock(async () => "ok");

    stack.before(async () => ({ decision: "deny" as const, reason: "auth failed" }));

    const result = await stack.execute(makeCtx(), terminal);

    expect(terminal).not.toHaveBeenCalled();
    expect(result).toMatchObject({ decision: "deny" });
  });

  test("after() helper runs after terminal", async () => {
    const stack = new MiddlewareStack();
    const order: string[] = [];

    stack.after(async (_ctx, result) => {
      order.push("after");
      return result;
    });

    await stack.execute(makeCtx(), async () => {
      order.push("terminal");
      return null;
    });

    expect(order).toEqual(["terminal", "after"]);
  });

  test("createContext generates unique requestIds", () => {
    const ctx1 = MiddlewareStack.createContext("tool", {}, "/tmp");
    const ctx2 = MiddlewareStack.createContext("tool", {}, "/tmp");
    expect(ctx1.requestId).not.toBe(ctx2.requestId);
  });

  test("stack size reflects registered middleware count", () => {
    const stack = new MiddlewareStack();
    expect(stack.size).toBe(0);
    stack.use(async (_, next) => next());
    expect(stack.size).toBe(1);
    stack.use(async (_, next) => next());
    expect(stack.size).toBe(2);
  });
});
