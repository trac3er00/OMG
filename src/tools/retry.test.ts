import { describe, expect, test } from "bun:test";
import { withRetry } from "./retry.js";

function mockImmediateTimers() {
  const originalSetTimeout = globalThis.setTimeout;
  const delays: number[] = [];

  globalThis.setTimeout = ((
    handler: TimerHandler,
    timeout?: number,
    ...args: unknown[]
  ) => {
    delays.push(Number(timeout ?? 0));
    if (typeof handler === "function") {
      handler(...args);
    }
    return 0 as unknown as ReturnType<typeof setTimeout>;
  }) as unknown as typeof setTimeout;

  return {
    delays,
    restore() {
      globalThis.setTimeout = originalSetTimeout;
    },
  };
}

describe("withRetry", () => {
  test("succeeds on first attempt", async () => {
    const result = await withRetry(async () => "ok");
    expect(result).toBe("ok");
  });

  test("retries on failure and succeeds on third attempt", async () => {
    const timers = mockImmediateTimers();
    const warnings: string[] = [];
    const originalWarn = console.warn;
    console.warn = ((...args: unknown[]) => {
      warnings.push(args.map(String).join(" "));
    }) as typeof console.warn;

    let attempts = 0;
    try {
      const result = await withRetry(
        async () => {
          attempts += 1;
          if (attempts < 3) {
            throw new Error(`fail ${attempts}`);
          }
          return "done";
        },
        { baseDelayMs: 100, jitter: false },
      );

      expect(result).toBe("done");
      expect(attempts).toBe(3);
      expect(timers.delays).toEqual([100, 200]);
      expect(warnings).toHaveLength(2);
    } finally {
      timers.restore();
      console.warn = originalWarn;
    }
  });

  test("throws after maxAttempts exhausted", async () => {
    const timers = mockImmediateTimers();
    let attempts = 0;

    try {
      await expect(
        withRetry(
          async () => {
            attempts += 1;
            throw new Error("nope");
          },
          { maxAttempts: 2, baseDelayMs: 50, jitter: false },
        ),
      ).rejects.toThrow("retry attempts exhausted after 2/2");
      expect(attempts).toBe(2);
      expect(timers.delays).toEqual([50]);
    } finally {
      timers.restore();
    }
  });

  test("respects retryOn predicate", async () => {
    const timers = mockImmediateTimers();
    let attempts = 0;

    try {
      await expect(
        withRetry(
          async () => {
            attempts += 1;
            throw new Error("fatal");
          },
          {
            retryOn: () => false,
            baseDelayMs: 50,
            jitter: false,
          },
        ),
      ).rejects.toThrow("fatal");
      expect(attempts).toBe(1);
      expect(timers.delays).toEqual([]);
    } finally {
      timers.restore();
    }
  });

  test("exponential backoff increases delay", async () => {
    const timers = mockImmediateTimers();
    let attempts = 0;

    try {
      const result = await withRetry(
        async () => {
          attempts += 1;
          if (attempts < 3) {
            throw new Error("try again");
          }
          return "ok";
        },
        {
          baseDelayMs: 100,
          maxDelayMs: 1000,
          jitter: false,
        },
      );

      expect(result).toBe("ok");
      expect(timers.delays).toEqual([100, 200]);
      expect(timers.delays[1] ?? 0).toBeGreaterThan(timers.delays[0] ?? 0);
    } finally {
      timers.restore();
    }
  });
});
