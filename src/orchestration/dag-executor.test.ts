import { describe, expect, test } from "bun:test";
import { DagExecutor } from "./dag-executor.js";

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

describe("DagExecutor", () => {
  test("executes tasks in topological waves and streams completions", async () => {
    const releaseWaveOne = createDeferred();
    const bStarted = createDeferred();
    const cStarted = createDeferred();
    const startOrder: string[] = [];
    const completionOrder: string[] = [];

    const executor = DagExecutor.create({ concurrency: 4 })
      .addTask("A", [], async () => {
        startOrder.push("A");
        return "done-a";
      })
      .addTask("B", ["A"], async () => {
        startOrder.push("B");
        bStarted.resolve();
        await releaseWaveOne.promise;
        return "done-b";
      })
      .addTask("C", ["A"], async () => {
        startOrder.push("C");
        cStarted.resolve();
        await releaseWaveOne.promise;
        return "done-c";
      })
      .addTask("D", ["B", "C"], async () => {
        startOrder.push("D");
        return "done-d";
      });

    const consume = (async (): Promise<void> => {
      for await (const result of executor.execute()) {
        completionOrder.push(result.id);
      }
    })();

    await Promise.all([bStarted.promise, cStarted.promise]);
    expect(startOrder[0]).toBe("A");
    expect(startOrder).not.toContain("D");

    releaseWaveOne.resolve();
    await consume;

    expect(completionOrder[0]).toBe("A");
    expect(completionOrder.at(-1)).toBe("D");
    expect(new Set(completionOrder.slice(1, 3))).toEqual(new Set(["B", "C"]));
  });

  test("propagates failure to dependents and skips blocked tasks", async () => {
    const executed: string[] = [];

    const executor = DagExecutor.create({ concurrency: 4 })
      .addTask("A", [], async () => {
        executed.push("A");
        return "done-a";
      })
      .addTask("B", ["A"], async () => {
        executed.push("B");
        throw new Error("boom");
      })
      .addTask("C", ["A"], async () => {
        executed.push("C");
        return "done-c";
      })
      .addTask("D", ["B", "C"], async () => {
        executed.push("D");
        return "done-d";
      });

    const statuses = new Map<string, string>();
    for await (const result of executor.execute()) {
      statuses.set(result.id, result.status);
    }

    expect(executed).not.toContain("D");
    expect(statuses.get("B")).toBe("rejected");
    expect(statuses.get("D")).toBeUndefined();
  });
});
