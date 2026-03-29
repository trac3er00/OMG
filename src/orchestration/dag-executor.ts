export type DagTaskHandler = () => Promise<unknown>;

export interface DagTaskResult {
  readonly id: string;
  readonly status: "fulfilled" | "rejected" | "skipped";
  readonly wave: number;
  readonly value?: unknown;
  readonly reason?: string;
}

export interface DagExecutorOptions {
  readonly concurrency?: number;
}

interface TaskDefinition {
  readonly id: string;
  readonly deps: readonly string[];
  readonly handler: DagTaskHandler;
}

interface TaskCompletion {
  readonly id: string;
  readonly status: "fulfilled" | "rejected";
  readonly wave: number;
  readonly value?: unknown;
  readonly reason?: string;
}

export class DagExecutor {
  static create(options: DagExecutorOptions = {}): DagExecutor {
    return new DagExecutor(options);
  }

  private readonly concurrency: number;

  private readonly tasks = new Map<string, TaskDefinition>();

  constructor(options: DagExecutorOptions = {}) {
    const requestedConcurrency = options.concurrency ?? Number.POSITIVE_INFINITY;
    this.concurrency = Math.max(1, requestedConcurrency);
  }

  addTask(id: string, deps: string[], handler: DagTaskHandler): this {
    if (id.length === 0) {
      throw new Error("task id must not be empty");
    }

    if (this.tasks.has(id)) {
      throw new Error(`duplicate task id: ${id}`);
    }

    if (deps.includes(id)) {
      throw new Error(`task ${id} cannot depend on itself`);
    }

    this.tasks.set(id, {
      id,
      deps: [...deps],
      handler,
    });
    return this;
  }

  async *execute(): AsyncGenerator<DagTaskResult, void, void> {
    const taskIds = [...this.tasks.keys()];
    if (taskIds.length === 0) {
      return;
    }

    const dependents = new Map<string, string[]>();
    const unresolvedDeps = new Map<string, number>();
    const blockedByFailure = new Map<string, boolean>();
    const waveByTask = new Map<string, number>();

    for (const id of taskIds) {
      dependents.set(id, []);
      unresolvedDeps.set(id, 0);
      blockedByFailure.set(id, false);
      waveByTask.set(id, 0);
    }

    for (const [id, task] of this.tasks.entries()) {
      for (const dep of task.deps) {
        if (!this.tasks.has(dep)) {
          throw new Error(`task ${id} depends on unknown task ${dep}`);
        }
        unresolvedDeps.set(id, (unresolvedDeps.get(id) ?? 0) + 1);
        const downstream = dependents.get(dep);
        if (downstream !== undefined) {
          downstream.push(id);
        }
      }
    }

    for (const downstream of dependents.values()) {
      downstream.sort();
    }

    const ready: string[] = taskIds
      .filter((id) => (unresolvedDeps.get(id) ?? 0) === 0)
      .sort();

    const inFlight = new Map<string, Promise<TaskCompletion>>();
    const outputQueue: DagTaskResult[] = [];
    let settledCount = 0;

    const enqueueReady = (id: string): void => {
      ready.push(id);
      ready.sort();
    };

    const enqueueResult = (result: DagTaskResult): void => {
      outputQueue.push(result);
      settledCount += 1;
    };

    const resolveDependent = (id: string, parentWave: number, parentFailed: boolean): void => {
      const currentUnresolved = unresolvedDeps.get(id);
      if (currentUnresolved === undefined) {
        return;
      }

      unresolvedDeps.set(id, currentUnresolved - 1);
      const nextWave = Math.max(waveByTask.get(id) ?? 0, parentWave + 1);
      waveByTask.set(id, nextWave);

      if (parentFailed) {
        blockedByFailure.set(id, true);
      }

      if ((unresolvedDeps.get(id) ?? 0) !== 0) {
        return;
      }

      const wave = waveByTask.get(id) ?? 0;
      if (blockedByFailure.get(id) === true) {
        enqueueResult({
          id,
          status: "skipped",
          wave,
          reason: "dependency failed",
        });
        for (const dependent of dependents.get(id) ?? []) {
          resolveDependent(dependent, wave, true);
        }
        return;
      }

      enqueueReady(id);
    };

    const handleCompletion = (completion: TaskCompletion): void => {
      if (completion.status === "fulfilled") {
        enqueueResult({
          id: completion.id,
          status: "fulfilled",
          wave: completion.wave,
          value: completion.value,
        });
      } else {
        enqueueResult(
          completion.reason === undefined
            ? {
              id: completion.id,
              status: "rejected",
              wave: completion.wave,
            }
            : {
              id: completion.id,
              status: "rejected",
              wave: completion.wave,
              reason: completion.reason,
            },
        );
      }

      const parentFailed = completion.status === "rejected";
      for (const dependent of dependents.get(completion.id) ?? []) {
        resolveDependent(dependent, completion.wave, parentFailed);
      }
    };

    const launch = (id: string): void => {
      const task = this.tasks.get(id);
      if (task === undefined) {
        throw new Error(`missing task ${id}`);
      }
      const wave = waveByTask.get(id) ?? 0;

      const completionPromise = (async (): Promise<TaskCompletion> => {
        try {
          const value = await task.handler();
          return {
            id,
            status: "fulfilled",
            wave,
            value,
          };
        } catch (error) {
          const reason = error instanceof Error ? error.message : String(error);
          return {
            id,
            status: "rejected",
            wave,
            reason,
          };
        }
      })();

      inFlight.set(id, completionPromise);
    };

    while (settledCount < taskIds.length) {
      while (ready.length > 0 && inFlight.size < this.concurrency) {
        const next = ready.shift();
        if (next !== undefined) {
          launch(next);
        }
      }

      if (outputQueue.length === 0) {
        if (inFlight.size === 0) {
          throw new Error("cycle detected or unresolved dependencies");
        }

        const completion = await Promise.race(inFlight.values());
        inFlight.delete(completion.id);
        handleCompletion(completion);
      }

      const nextResult = outputQueue.shift();
      if (nextResult !== undefined) {
        yield nextResult;
      }
    }
  }
}
