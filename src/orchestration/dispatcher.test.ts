import { describe, expect, test } from "bun:test";
import type { WorkerTask } from "../interfaces/orchestration.js";
import { MAX_JOBS, SubagentDispatcher } from "./dispatcher.js";

interface Deferred {
  readonly promise: Promise<void>;
  resolve: () => void;
}

function createDeferred(): Deferred {
  let resolve: (() => void) | undefined;
  const promise = new Promise<void>((innerResolve) => {
    resolve = innerResolve;
  });
  return {
    promise,
    resolve: () => {
      resolve?.();
    },
  };
}

function makeTask(index: number): WorkerTask {
  return {
    agentName: `agent-${index}`,
    prompt: `prompt-${index}`,
  };
}

describe("SubagentDispatcher", () => {
  test("enforces 100-job limit", async () => {
    const gates = Array.from({ length: MAX_JOBS }, () => createDeferred());
    let gateIndex = 0;
    const dispatcher = SubagentDispatcher.create({
      maxJobs: MAX_JOBS,
      concurrency: MAX_JOBS,
      runner: async (_task, context) => {
        context.emitArtifact({
          type: "worker-result",
          producedAt: new Date().toISOString(),
          payload: { accepted: true },
        });
        const gate = gates[gateIndex];
        gateIndex += 1;
        if (gate !== undefined) {
          await gate.promise;
        }
        return { exitCode: 0 };
      },
    });

    const handles = await Promise.all(
      Array.from({ length: MAX_JOBS }, async (_, index) => dispatcher.dispatch(makeTask(index))),
    );

    let overflowError: string | undefined;
    try {
      await dispatcher.dispatch(makeTask(MAX_JOBS));
    } catch (error) {
      overflowError = error instanceof Error ? error.message : String(error);
    }
    expect(overflowError).toContain("max jobs exceeded");

    for (const gate of gates) {
      gate.resolve();
    }

    const results = await Promise.all(handles.map((handle) => handle.completion));
    expect(results.every((result) => result.status === "completed")).toBe(true);
  });

  test("dispatch emits artifacts via async iterator", async () => {
    const dispatcher = SubagentDispatcher.create({
      runner: async (task, context) => {
        context.emitArtifact({
          type: "worker-result",
          producedAt: new Date().toISOString(),
          payload: { prompt: task.prompt, agent: task.agentName },
        });
        return { exitCode: 0 };
      },
    });

    const handle = await dispatcher.dispatch(makeTask(0));
    const artifacts: Array<{ type: string; payload: Readonly<Record<string, unknown>> }> = [];

    for await (const artifact of handle.artifacts) {
      artifacts.push({ type: artifact.type, payload: artifact.payload });
    }

    const completion = await handle.completion;

    expect(completion.status).toBe("completed");
    expect(artifacts).toEqual([
      {
        type: "worker-result",
        payload: { prompt: "prompt-0", agent: "agent-0" },
      },
    ]);
  });
});
