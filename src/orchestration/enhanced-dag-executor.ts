import {
  DagExecutor,
  type DagTaskHandler,
  type DagTaskResult,
  type DagExecutorOptions,
} from "./dag-executor.js";

export type TaskPriority = "high" | "medium" | "low";

export interface EnhancedTaskOptions {
  readonly timeout_ms?: number;
  readonly priority?: TaskPriority;
  readonly max_retries?: number;
}

export interface CircuitBreakerState {
  readonly task_id: string;
  readonly failure_count: number;
  readonly state: "closed" | "open" | "half-open";
  readonly cooldown_until?: number;
}

export interface EnhancedDagExecutorOptions extends DagExecutorOptions {
  readonly default_timeout_ms?: number;
  readonly circuit_breaker_threshold?: number;
  readonly circuit_breaker_cooldown_ms?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_CB_THRESHOLD = 5;
const DEFAULT_CB_COOLDOWN_MS = 60_000;
export const PRIORITY_ORDER: Record<TaskPriority, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

export class EnhancedDagExecutor {
  private readonly inner: DagExecutor;
  private readonly taskOptions = new Map<
    string,
    Required<EnhancedTaskOptions>
  >();
  private readonly circuitBreakers = new Map<string, CircuitBreakerState>();
  private readonly defaultTimeoutMs: number;
  private readonly cbThreshold: number;
  private readonly cbCooldownMs: number;

  constructor(opts: EnhancedDagExecutorOptions = {}) {
    this.inner = DagExecutor.create(opts);
    this.defaultTimeoutMs = opts.default_timeout_ms ?? DEFAULT_TIMEOUT_MS;
    this.cbThreshold = opts.circuit_breaker_threshold ?? DEFAULT_CB_THRESHOLD;
    this.cbCooldownMs =
      opts.circuit_breaker_cooldown_ms ?? DEFAULT_CB_COOLDOWN_MS;
  }

  static create(opts: EnhancedDagExecutorOptions = {}): EnhancedDagExecutor {
    return new EnhancedDagExecutor(opts);
  }

  addTask(
    id: string,
    deps: string[],
    handler: DagTaskHandler,
    opts: EnhancedTaskOptions = {},
  ): this {
    const timeout_ms = opts.timeout_ms ?? this.defaultTimeoutMs;
    const priority = opts.priority ?? "medium";
    const max_retries = opts.max_retries ?? 0;

    this.taskOptions.set(id, { timeout_ms, priority, max_retries });

    const wrappedHandler = async (): Promise<unknown> => {
      const cb = this.circuitBreakers.get(id);
      if (cb != null && cb.state === "open") {
        const now = Date.now();
        if (cb.cooldown_until != null && now < cb.cooldown_until) {
          throw new Error(`circuit_open:${id}`);
        }
        this.circuitBreakers.set(id, { ...cb, state: "half-open" });
      }

      try {
        const result = await this.withTimeout(handler, timeout_ms, id);
        if (cb != null) {
          this.circuitBreakers.set(id, {
            task_id: id,
            failure_count: 0,
            state: "closed",
          });
        }
        return result;
      } catch (err) {
        this.recordFailure(id);
        throw err;
      }
    };

    this.inner.addTask(id, deps, wrappedHandler);
    return this;
  }

  async *execute(): AsyncGenerator<DagTaskResult, void, void> {
    yield* this.inner.execute();
  }

  getCircuitBreakerState(taskId: string): CircuitBreakerState | null {
    return this.circuitBreakers.get(taskId) ?? null;
  }

  private async withTimeout(
    handler: DagTaskHandler,
    timeoutMs: number,
    taskId: string,
  ): Promise<unknown> {
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`timeout:${taskId}:${timeoutMs}ms`));
      }, timeoutMs);

      handler()
        .then((value) => {
          clearTimeout(timer);
          resolve(value);
        })
        .catch((err: unknown) => {
          clearTimeout(timer);
          reject(err);
        });
    });
  }

  private recordFailure(taskId: string): void {
    const current = this.circuitBreakers.get(taskId) ?? {
      task_id: taskId,
      failure_count: 0,
      state: "closed" as const,
    };

    const newCount = current.failure_count + 1;
    if (newCount >= this.cbThreshold) {
      this.circuitBreakers.set(taskId, {
        task_id: taskId,
        failure_count: newCount,
        state: "open",
        cooldown_until: Date.now() + this.cbCooldownMs,
      });
    } else {
      this.circuitBreakers.set(taskId, {
        ...current,
        failure_count: newCount,
        state: "closed",
      });
    }
  }
}

export async function collectResults(
  executor: EnhancedDagExecutor | DagExecutor,
): Promise<DagTaskResult[]> {
  const results: DagTaskResult[] = [];
  for await (const result of executor.execute()) {
    results.push(result);
  }
  return results;
}
