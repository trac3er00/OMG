import { randomUUID } from "node:crypto";
import type { WorkerTask } from "../interfaces/orchestration.js";

export interface ExecKernelRunState {
  readonly runId: string;
  readonly task: WorkerTask;
  readonly startedAt: string;
  readonly finishedAt: string;
  readonly stateNamespace: Readonly<Record<string, unknown>>;
}

export interface ExecKernelRunContext {
  readonly runId: string;
  getState<T>(key: string): T | undefined;
  setState(key: string, value: unknown): void;
  snapshot(): Readonly<Record<string, unknown>>;
}

export interface ExecKernelExecutor {
  execute(task: WorkerTask, context: ExecKernelRunContext): Promise<unknown>;
}

export interface ExecKernelDeps {
  readonly now?: () => Date;
  readonly createRunId?: () => string;
  readonly executor?: ExecKernelExecutor;
}

class PassthroughExecutor implements ExecKernelExecutor {
  async execute(task: WorkerTask): Promise<unknown> {
    return {
      status: "ok",
      agentName: task.agentName,
      prompt: task.prompt,
      order: task.order,
      timeout: task.timeout,
    };
  }
}

export class ExecKernel {
  static create(deps: ExecKernelDeps = {}): ExecKernel {
    return new ExecKernel(deps);
  }

  private readonly now: () => Date;
  private readonly createRunId: () => string;
  private readonly executor: ExecKernelExecutor;
  private readonly runState = new Map<string, ExecKernelRunState>();

  constructor(deps: ExecKernelDeps = {}) {
    this.now = deps.now ?? (() => new Date());
    this.createRunId = deps.createRunId ?? (() => randomUUID());
    this.executor = deps.executor ?? new PassthroughExecutor();
  }

  async run(task: WorkerTask): Promise<ExecKernelRunState> {
    const runId = this.createRunId();
    const startedAt = this.now().toISOString();
    const namespace = new Map<string, unknown>();
    const context: ExecKernelRunContext = {
      runId,
      getState: <T>(key: string): T | undefined => {
        return namespace.get(key) as T | undefined;
      },
      setState: (key: string, value: unknown): void => {
        namespace.set(key, value);
      },
      snapshot: (): Readonly<Record<string, unknown>> => {
        return Object.fromEntries(namespace.entries());
      },
    };

    await this.executor.execute(task, context);

    const state: ExecKernelRunState = {
      runId,
      task,
      startedAt,
      finishedAt: this.now().toISOString(),
      stateNamespace: context.snapshot(),
    };
    this.runState.set(runId, state);
    return state;
  }

  getRunState(runId: string): ExecKernelRunState | undefined {
    return this.runState.get(runId);
  }
}
