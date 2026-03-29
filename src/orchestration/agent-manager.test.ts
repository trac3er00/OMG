import { spawn } from "node:child_process";
import { describe, expect, test } from "bun:test";
import type { AgentConfig } from "../interfaces/orchestration.js";
import { AgentManager, AgentState } from "./agent-manager.js";

const DEFAULT_CONFIG: AgentConfig = {
  name: "test-agent",
  category: "orchestration",
  prompt: "run",
  skills: [],
  timeout: 5,
  maxRetries: 1,
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function waitForState(
  manager: AgentManager,
  id: string,
  expected: AgentState,
  timeoutMs: number,
): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const state = await manager.getState(id);
    if (state === expected) {
      return;
    }
    await sleep(10);
  }

  const state = await manager.getState(id);
  throw new Error(`Expected state ${expected}, got ${String(state)}`);
}

describe("AgentManager", () => {
  test("transitions PENDING -> RUNNING -> COMPLETED", async () => {
    const manager = AgentManager.create({
      spawnProcess: () =>
        spawn(process.execPath, ["-e", "setTimeout(() => process.exit(0), 40);"], {
          stdio: ["ignore", "pipe", "pipe"],
        }),
    });

    const id = await manager.spawnAgent(DEFAULT_CONFIG);
    const initial = await manager.getState(id);
    expect(initial === AgentState.PENDING || initial === AgentState.RUNNING).toBe(true);

    await waitForState(manager, id, AgentState.RUNNING, 500);
    await waitForState(manager, id, AgentState.COMPLETED, 1_500);
  });

  test("cancel transitions RUNNING -> CANCELLED", async () => {
    const manager = AgentManager.create({
      spawnProcess: () =>
        spawn(process.execPath, ["-e", "setTimeout(() => process.exit(0), 10_000);"], {
          stdio: ["ignore", "pipe", "pipe"],
        }),
      cancelKillDelayMs: 25,
    });

    const id = await manager.spawnAgent(DEFAULT_CONFIG);

    await waitForState(manager, id, AgentState.RUNNING, 800);

    const cancelled = await manager.cancelAgent(id);
    expect(cancelled).toBe(true);

    await waitForState(manager, id, AgentState.CANCELLED, 1_000);
  });
});
