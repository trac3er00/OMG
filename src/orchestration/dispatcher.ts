import PQueue from "p-queue";
import type { IsolationMode, WorkerTask } from "../interfaces/orchestration.js";

export const MAX_JOBS = 100;

export interface DispatchArtifact {
  readonly type: string;
  readonly producedAt: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

export interface DispatchResult {
  readonly jobId: string;
  readonly status: "completed" | "failed";
  readonly exitCode: number;
  readonly error?: string;
}

export interface DispatchContext {
  readonly jobId: string;
  readonly isolation: Exclude<IsolationMode, "container">;
  emitArtifact: (artifact: DispatchArtifact) => void;
}

export type DispatchRunner = (
  task: WorkerTask,
  context: DispatchContext,
) => Promise<{ readonly exitCode: number }>;

export interface DispatchHandle {
  readonly id: string;
  readonly completion: Promise<DispatchResult>;
  readonly artifacts: AsyncIterable<DispatchArtifact>;
}

export interface SubagentDispatcherOptions {
  readonly maxJobs?: number;
  readonly concurrency?: number;
  readonly isolation?: Exclude<IsolationMode, "container">;
  readonly runner?: DispatchRunner;
  readonly idGenerator?: () => string;
}

class AsyncMutex {
  private locked = false;

  private readonly waiters: Array<() => void> = [];

  async acquire(): Promise<() => void> {
    if (!this.locked) {
      this.locked = true;
      return this.release;
    }

    await new Promise<void>((resolve) => {
      this.waiters.push(resolve);
    });
    this.locked = true;
    return this.release;
  }

  private readonly release = (): void => {
    const waiter = this.waiters.shift();
    if (waiter === undefined) {
      this.locked = false;
      return;
    }
    waiter();
  };
}

class ArtifactStream implements AsyncIterable<DispatchArtifact> {
  private readonly buffered: DispatchArtifact[] = [];

  private readonly waiters: Array<(result: IteratorResult<DispatchArtifact>) => void> = [];

  private closed = false;

  push(artifact: DispatchArtifact): void {
    if (this.closed) {
      return;
    }

    const waiter = this.waiters.shift();
    if (waiter === undefined) {
      this.buffered.push(artifact);
      return;
    }

    waiter({ done: false, value: artifact });
  }

  close(): void {
    if (this.closed) {
      return;
    }

    this.closed = true;
    while (this.waiters.length > 0) {
      const waiter = this.waiters.shift();
      if (waiter !== undefined) {
        waiter({ done: true, value: undefined });
      }
    }
  }

  [Symbol.asyncIterator](): AsyncIterator<DispatchArtifact> {
    return {
      next: async (): Promise<IteratorResult<DispatchArtifact>> => {
        const bufferedArtifact = this.buffered.shift();
        if (bufferedArtifact !== undefined) {
          return { done: false, value: bufferedArtifact };
        }

        if (this.closed) {
          return { done: true, value: undefined };
        }

        return new Promise<IteratorResult<DispatchArtifact>>((resolve) => {
          this.waiters.push(resolve);
        });
      },
    };
  }
}

interface InternalJob {
  readonly stream: ArtifactStream;
  completion?: Promise<DispatchResult>;
}

function defaultIdGenerator(): string {
  return crypto.randomUUID();
}

async function defaultRunner(
  task: WorkerTask,
  context: DispatchContext,
): Promise<{ readonly exitCode: number }> {
  context.emitArtifact({
    type: "worker-result",
    producedAt: new Date().toISOString(),
    payload: {
      agent: task.agentName,
      prompt: task.prompt,
      isolation: context.isolation,
    },
  });
  return { exitCode: 0 };
}

export class SubagentDispatcher {
  static create(options: SubagentDispatcherOptions = {}): SubagentDispatcher {
    return new SubagentDispatcher(options);
  }

  private readonly maxJobs: number;

  private readonly isolation: Exclude<IsolationMode, "container">;

  private readonly queue: PQueue;

  private readonly mutex = new AsyncMutex();

  private readonly jobs = new Map<string, InternalJob>();

  private readonly runner: DispatchRunner;

  private readonly idGenerator: () => string;

  constructor(options: SubagentDispatcherOptions = {}) {
    this.maxJobs = options.maxJobs ?? MAX_JOBS;
    this.isolation = options.isolation ?? "none";
    this.queue = new PQueue({ concurrency: options.concurrency ?? this.maxJobs });
    this.runner = options.runner ?? defaultRunner;
    this.idGenerator = options.idGenerator ?? defaultIdGenerator;
  }

  async dispatch(task: WorkerTask): Promise<DispatchHandle> {
    const release = await this.mutex.acquire();
    const jobId = this.idGenerator();
    const stream = new ArtifactStream();

    try {
      if (this.jobs.size >= this.maxJobs) {
        throw new Error("max jobs exceeded");
      }

      const entry: InternalJob = { stream };
      this.jobs.set(jobId, entry);
      entry.completion = this.queue.add(async () => {
        try {
          const result = await this.runner(task, {
            jobId,
            isolation: this.isolation,
            emitArtifact: (artifact) => {
              stream.push(artifact);
            },
          });

          return {
            jobId,
            status: "completed",
            exitCode: result.exitCode,
          } as const;
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          stream.push({
            type: "worker-error",
            producedAt: new Date().toISOString(),
            payload: { message },
          });
          return {
            jobId,
            status: "failed",
            exitCode: 1,
            error: message,
          } as const;
        } finally {
          stream.close();
          const cleanupRelease = await this.mutex.acquire();
          try {
            this.jobs.delete(jobId);
          } finally {
            cleanupRelease();
          }
        }
      });
    } finally {
      release();
    }

    const completion = this.jobs.get(jobId)?.completion;
    if (completion === undefined) {
      throw new Error(`failed to create job ${jobId}`);
    }

    return {
      id: jobId,
      completion,
      artifacts: stream,
    };
  }
}
