import { describe, expect, test } from "bun:test";
import { denyDecision } from "./common.js";
import {
  HookLifecycleManager,
  type HookLifecycleContext,
} from "./lifecycle.js";
import type { HookResult } from "../interfaces/hooks.js";

function makeContext(
  overrides: Partial<HookLifecycleContext> = {},
): HookLifecycleContext {
  return {
    projectDir: "/tmp/omg-project",
    timestamp: new Date().toISOString(),
    sessionId: "session-123",
    toolName: "Write",
    toolInput: { path: "file.txt" },
    ...overrides,
  };
}

describe("HookLifecycleManager", () => {
  test("pre-tool hook fires before tool execution", async () => {
    const manager = HookLifecycleManager.create();
    const events: string[] = [];

    manager.registerHook("pre-tool", async () => {
      events.push("pre-tool");
      return { decision: { action: "allow", reason: "ok", riskLevel: "low", tags: [] } };
    });

    const runTool = async (): Promise<void> => {
      const preResult = await manager.runPreTool(makeContext());
      if (preResult.decision.action === "deny" || preResult.decision.action === "block") {
        return;
      }
      events.push("tool");
    };

    await runTool();

    expect(events).toEqual(["pre-tool", "tool"]);
  });

  test("deny from pre-tool blocks tool execution", async () => {
    const manager = HookLifecycleManager.create();
    const events: string[] = [];

    manager.registerHook("pre-tool", async () => {
      events.push("pre-tool");
      return denyDecision("blocked by policy");
    });

    const runTool = async (): Promise<void> => {
      const preResult = await manager.runPreTool(makeContext());
      if (preResult.decision.action === "deny" || preResult.decision.action === "block") {
        return;
      }
      events.push("tool");
    };

    await runTool();

    expect(events).toEqual(["pre-tool"]);
  });

  test("hooks run in explicit priority order", async () => {
    const manager = HookLifecycleManager.create();
    const calls: number[] = [];

    manager.registerHook(
      "session-start",
      async () => {
        calls.push(30);
        return { decision: { action: "allow", reason: "late", riskLevel: "low", tags: [] } };
      },
      30,
    );
    manager.registerHook(
      "session-start",
      async () => {
        calls.push(10);
        return { decision: { action: "allow", reason: "early", riskLevel: "low", tags: [] } };
      },
      10,
    );
    manager.registerHook(
      "session-start",
      async () => {
        calls.push(20);
        return { decision: { action: "allow", reason: "middle", riskLevel: "low", tags: [] } };
      },
      20,
    );

    await manager.runSessionStart(makeContext());

    expect(calls).toEqual([10, 20, 30]);
  });

  test("settings hook registration order determines default ordering", async () => {
    const manager = new HookLifecycleManager({
      hookRegistrations: {
        "pre-tool": ["firstHook", "secondHook"],
      },
    });
    const calls: string[] = [];

    async function secondHook(): Promise<HookResult> {
      calls.push("second");
      return { decision: { action: "allow", reason: "second", riskLevel: "low", tags: [] } };
    }

    async function firstHook(): Promise<HookResult> {
      calls.push("first");
      return { decision: { action: "allow", reason: "first", riskLevel: "low", tags: [] } };
    }

    manager.registerHook("pre-tool", secondHook);
    manager.registerHook("pre-tool", firstHook);

    await manager.runPreTool(makeContext());

    expect(calls).toEqual(["first", "second"]);
  });
});
