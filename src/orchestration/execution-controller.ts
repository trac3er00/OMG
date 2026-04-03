import {
  EnhancedDagExecutor,
  type EnhancedTaskOptions,
} from "./enhanced-dag-executor.js";
import { type DagTaskResult } from "./dag-executor.js";
import { recommendAgent, scoreComplexity } from "./decision-engine.js";

export type OrchestrationMode = "ultrawork" | "team" | "sequential";
export type SessionStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export const DEFAULT_CONCURRENCY: Record<OrchestrationMode, number> = {
  ultrawork: 8,
  team: 4,
  sequential: 1,
};

export interface ExecutableTask {
  readonly id: string;
  readonly prompt: string;
  readonly deps: readonly string[];
  readonly category?: string | undefined;
  readonly skills: readonly string[];
  readonly priority: "high" | "medium" | "low";
  readonly timeout_ms: number;
}

export interface RegisteredTaskMeta {
  readonly taskId: string;
  readonly category: string;
  readonly complexity: string;
  readonly deps: readonly string[];
  readonly provider: string;
  readonly reasoning: string;
}

export class ExecutionController {
  readonly mode: OrchestrationMode;
  readonly concurrency: number;

  private readonly dag: EnhancedDagExecutor;

  constructor(mode: OrchestrationMode, concurrency?: number) {
    this.mode = mode;
    this.concurrency = concurrency ?? DEFAULT_CONCURRENCY[mode];
    this.dag = EnhancedDagExecutor.create({
      concurrency: this.concurrency,
      default_timeout_ms: 120_000,
      circuit_breaker_threshold: 3,
    });
  }

  registerTask<TTask extends ExecutableTask>(
    task: TTask,
    runTask: (task: TTask, category: string) => Promise<unknown>,
  ): RegisteredTaskMeta {
    const recommendation = recommendAgent(task.prompt);
    const category = task.category ?? recommendation.category;

    const dagOptions: EnhancedTaskOptions = {
      timeout_ms: task.timeout_ms,
      priority: task.priority,
    };

    this.dag.addTask(
      task.id,
      [...task.deps],
      () => runTask(task, category),
      dagOptions,
    );

    return {
      taskId: task.id,
      category,
      complexity: scoreComplexity(task.prompt),
      deps: task.deps,
      provider: recommendation.provider,
      reasoning: recommendation.reasoning,
    };
  }

  async *execute(): AsyncGenerator<DagTaskResult, void, void> {
    yield* this.dag.execute();
  }
}
