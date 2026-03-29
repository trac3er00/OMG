import { describe, test, expect } from "bun:test";
import {
  HookReentryGuard,
  setupCrashHandler,
  isBypassMode,
  denyDecision,
  blockDecision,
  allowDecision,
  checkPerformanceBudget,
  bootstrapRuntimePaths,
} from "./common.js";
import type { HookResult, HookContext } from "../interfaces/hooks.js";

function makeCtx(overrides: Partial<HookContext> = {}): HookContext {
  return {
    phase: "pre_tool",
    projectDir: "/test/project",
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe("HookReentryGuard", () => {
  test("first acquisition succeeds", async () => {
    const guard = new HookReentryGuard();
    const release = await guard.acquire("test-hook");
    expect(release).toBeDefined();
    await release();
  });

  test("concurrent acquisition blocked", async () => {
    const guard = new HookReentryGuard();
    const release = await guard.acquire("test-hook");

    try {
      await guard.acquire("test-hook", { waitMs: 0 });
      expect(true).toBe(false); // should not reach here
    } catch (err) {
      expect((err as Error).message).toContain("Reentrant");
    } finally {
      await release();
    }
  });

  test("different hooks don't block each other", async () => {
    const guard = new HookReentryGuard();
    const r1 = await guard.acquire("hook-a");
    const r2 = await guard.acquire("hook-b"); // different hook — should succeed
    await r1();
    await r2();
  });

  test("release allows re-acquisition", async () => {
    const guard = new HookReentryGuard();
    const release = await guard.acquire("test-hook");
    await release();
    const release2 = await guard.acquire("test-hook");
    await release2();
  });
});

describe("setupCrashHandler", () => {
  test("security hook fail-closed: error → deny", async () => {
    const handler = setupCrashHandler("firewall", true);
    const ctx = makeCtx();
    const result = await handler(ctx, async () => {
      throw new Error("crash");
    });
    expect(result.decision.action).toBe("deny");
  });

  test("non-security hook fail-open: error → allow", async () => {
    const handler = setupCrashHandler("analytics", false);
    const ctx = makeCtx();
    const result = await handler(ctx, async () => {
      throw new Error("crash");
    });
    expect(result.decision.action).toBe("allow");
  });

  test("no error: result passes through", async () => {
    const handler = setupCrashHandler("firewall", true);
    const ctx = makeCtx();
    const expected: HookResult = {
      decision: { action: "allow", reason: "ok", riskLevel: "low", tags: [] },
    };
    const result = await handler(ctx, async () => expected);
    expect(result.decision.action).toBe("allow");
  });

  test("fail-closed includes hook name in reason", async () => {
    const handler = setupCrashHandler("secret-guard", true);
    const ctx = makeCtx();
    const result = await handler(ctx, async () => {
      throw new Error("boom");
    });
    expect(result.decision.reason).toContain("secret-guard");
    expect(result.decision.reason).toContain("fail-closed");
  });

  test("fail-open includes hook name in reason", async () => {
    const handler = setupCrashHandler("analytics", false);
    const ctx = makeCtx();
    const result = await handler(ctx, async () => {
      throw new Error("oops");
    });
    expect(result.decision.reason).toContain("analytics");
    expect(result.decision.reason).toContain("fail-open");
  });
});

describe("denyDecision / blockDecision / allowDecision", () => {
  test("denyDecision returns deny action", () => {
    const r = denyDecision("test reason");
    expect(r.decision.action).toBe("deny");
    expect(r.decision.reason).toBe("test reason");
    expect(r.decision.riskLevel).toBe("high");
  });

  test("blockDecision returns block action", () => {
    const r = blockDecision("blocked");
    expect(r.decision.action).toBe("block");
    expect(r.decision.reason).toBe("blocked");
    expect(r.decision.riskLevel).toBe("critical");
  });

  test("allowDecision returns allow action", () => {
    const r = allowDecision("ok");
    expect(r.decision.action).toBe("allow");
    expect(r.decision.reason).toBe("ok");
    expect(r.decision.riskLevel).toBe("low");
  });
});

describe("isBypassMode", () => {
  test("bypass=true in data → true", () => {
    expect(isBypassMode({ bypass: true })).toBe(true);
  });

  test("bypass absent → false", () => {
    expect(isBypassMode({ tool: "Read" })).toBe(false);
  });

  test("empty object → false", () => {
    expect(isBypassMode({})).toBe(false);
  });

  test("bypass=false → false", () => {
    expect(isBypassMode({ bypass: false })).toBe(false);
  });

  test("permission_mode bypasspermissions → true", () => {
    expect(isBypassMode({ permission_mode: "bypasspermissions" })).toBe(true);
  });

  test("permission_mode dontask → true", () => {
    expect(isBypassMode({ permission_mode: "dontask" })).toBe(true);
  });

  test("permission_mode other → false", () => {
    expect(isBypassMode({ permission_mode: "normal" })).toBe(false);
  });
});

describe("checkPerformanceBudget", () => {
  test("within budget returns true", () => {
    const start = Date.now() - 50;
    expect(checkPerformanceBudget(start, "test-hook")).toBe(true);
  });

  test("over budget returns false", () => {
    const start = Date.now() - 200;
    expect(checkPerformanceBudget(start, "slow-hook")).toBe(false);
  });
});

describe("bootstrapRuntimePaths", () => {
  test("returns projectDir, stateDir, omgDir", () => {
    const result = bootstrapRuntimePaths("/tmp/test-project");
    expect(result.projectDir).toBe("/tmp/test-project");
    expect(result.omgDir).toBe("/tmp/test-project/.omg");
    expect(result.stateDir).toBe("/tmp/test-project/.omg/state");
  });
});
