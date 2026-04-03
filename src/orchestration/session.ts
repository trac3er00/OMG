import { EventEmitter } from "node:events";
import { z } from "zod";
import {
  AgentManager,
  AgentState,
  type AgentRunResult,
} from "./agent-manager.js";
import {
  EnhancedDagExecutor,
  type EnhancedTaskOptions,
} from "./enhanced-dag-executor.js";
import { type DagTaskResult } from "./dag-executor.js";
import { recommendAgent, scoreComplexity } from "./decision-engine.js";
import { BudgetEnvelope, type BudgetLimits } from "./budget.js";
import { WorkerWatchdog } from "./watchdog.js";
import { ResourceLockManager, type ResourceLockPriority } from "./deadlock.js";

export type OrchestrationMode = "ultrawork" | "team" | "sequential";
export type SessionStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export const OrchestrationTaskSchema = z.object({
  id: z.string().min(1),
  prompt: z.string().min(1),
  deps: z.array(z.string()).default([]),
  category: z.string().optional(),
  skills: z.array(z.string()).default([]),
  priority: z.enum(["high", "medium", "low"]).default("medium"),
  timeout_ms: z.number().positive().default(120_000),
});
export type OrchestrationTask = z.infer<typeof OrchestrationTaskSchema>;

export interface SessionEvent {
  readonly type: string;
  readonly timestamp: string;
  readonly sessionId: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

export interface AgentStatus {
  readonly agentId: string;
  readonly taskId: string;
  readonly state: AgentState;
  readonly category: string;
  readonly prompt: string;
  readonly startedAt?: string;
  readonly elapsedMs: number;
  readonly result?: AgentRunResult;
}

export interface SessionSnapshot {
  readonly sessionId: string;
  readonly mode: OrchestrationMode;
  readonly status: SessionStatus;
  readonly startedAt: string;
  readonly elapsedMs: number;
  readonly agents: readonly AgentStatus[];
  readonly tasksTotal: number;
  readonly tasksCompleted: number;
  readonly tasksFailed: number;
  readonly tasksSkipped: number;
  readonly budgetPressure: Readonly<Record<string, number>>;
  readonly events: readonly SessionEvent[];
}

export interface OrchestrationSessionOptions {
  readonly mode?: OrchestrationMode;
  readonly budgetLimits?: BudgetLimits;
  readonly concurrency?: number;
  readonly watchdogThresholdMs?: number;
  readonly projectDir?: string;
  readonly idGenerator?: () => string;
  readonly now?: () => Date;
  readonly maxEvents?: number;
}

const DEFAULT_CONCURRENCY: Record<OrchestrationMode, number> = {
  ultrawork: 8,
  team: 4,
  sequential: 1,
};

const DEFAULT_BUDGET: BudgetLimits = {
  tokens: 500_000,
  wall_time_ms: 600_000,
  memory_mb: 2048,
};

const DEFAULT_WATCHDOG_THRESHOLD_MS = 60_000;
const MAX_EVENTS = 500;

export class OrchestrationSession extends EventEmitter {
  static create(
    options: OrchestrationSessionOptions = {},
  ): OrchestrationSession {
    return new OrchestrationSession(options);
  }

  readonly sessionId: string;
  readonly mode: OrchestrationMode;

  private status: SessionStatus = "idle";
  private startedAt: string = "";
  private startMs = 0;

  private readonly agentManager: AgentManager;
  private readonly dag: EnhancedDagExecutor;
  private readonly budget: BudgetEnvelope;
  private readonly watchdog: WorkerWatchdog;
  private readonly lockManager: ResourceLockManager;
  private readonly now: () => Date;
  private readonly concurrency: number;
  private readonly watchdogThresholdMs: number;
  private readonly maxEvents: number;

  private readonly agentMap = new Map<
    string,
    { taskId: string; category: string; prompt: string; startedAt: string }
  >();
  private readonly taskResults = new Map<string, DagTaskResult>();
  private readonly events: SessionEvent[] = [];
  private watchdogInterval: ReturnType<typeof setInterval> | null = null;

  constructor(options: OrchestrationSessionOptions = {}) {
    super();

    this.now = options.now ?? (() => new Date());
    const idGen =
      options.idGenerator ?? (() => `orch-${crypto.randomUUID().slice(0, 12)}`);
    this.sessionId = idGen();
    this.mode = options.mode ?? "ultrawork";
    this.concurrency = options.concurrency ?? DEFAULT_CONCURRENCY[this.mode];
    this.watchdogThresholdMs =
      options.watchdogThresholdMs ?? DEFAULT_WATCHDOG_THRESHOLD_MS;
    this.maxEvents = options.maxEvents ?? MAX_EVENTS;

    this.agentManager = AgentManager.create({
      projectDir: options.projectDir ?? process.cwd(),
      now: this.now,
    });

    this.dag = EnhancedDagExecutor.create({
      concurrency: this.concurrency,
      default_timeout_ms: 120_000,
      circuit_breaker_threshold: 3,
    });

    this.budget = BudgetEnvelope.create(
      this.sessionId,
      options.budgetLimits ?? DEFAULT_BUDGET,
    );

    this.watchdog = WorkerWatchdog.create({ now: () => this.now().getTime() });
    this.lockManager = new ResourceLockManager();
  }

  async *orchestrate(
    tasks: readonly OrchestrationTask[],
  ): AsyncGenerator<DagTaskResult, void, void> {
    if (this.status === "running") {
      throw new Error("Session already running");
    }

    this.status = "running";
    this.startedAt = this.now().toISOString();
    this.startMs = this.now().getTime();
    this.emitEvent("session_started", {
      mode: this.mode,
      taskCount: tasks.length,
      concurrency: this.concurrency,
    });

    this.startWatchdog();

    try {
      for (const task of tasks) {
        const validated = OrchestrationTaskSchema.parse(task);
        const recommendation = recommendAgent(validated.prompt);
        const category = validated.category ?? recommendation.category;

        const dagOptions: EnhancedTaskOptions = {
          timeout_ms: validated.timeout_ms,
          priority: validated.priority,
        };

        this.dag.addTask(
          validated.id,
          [...validated.deps],
          () => this.executeTask(validated, category),
          dagOptions,
        );

        this.emitEvent("task_registered", {
          taskId: validated.id,
          category,
          complexity: scoreComplexity(validated.prompt),
          deps: validated.deps,
          provider: recommendation.provider,
          reasoning: recommendation.reasoning,
        });
      }

      for await (const result of this.dag.execute()) {
        this.taskResults.set(result.id, result);
        this.budget.record("wall_time_ms", this.now().getTime() - this.startMs);

        this.emitEvent("task_result", {
          taskId: result.id,
          status: result.status,
          wave: result.wave,
          reason: result.reason,
        });

        const budgetCheck = this.budget.check();
        if (budgetCheck.exceeded) {
          this.emitEvent("budget_exceeded", {
            dimensions: budgetCheck.dimensions,
            snapshot: this.budget.toSnapshot(),
          });
        }

        yield result;
      }

      this.status = "completed";
      this.emitEvent("session_completed", this.getSummary());
    } catch (error) {
      this.status = "failed";
      this.emitEvent("session_failed", {
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      this.stopWatchdog();
    }
  }

  async cancel(): Promise<void> {
    if (this.status !== "running") return;

    this.status = "cancelled";
    for (const [agentId] of this.agentMap) {
      await this.agentManager.cancelAgent(agentId);
    }
    this.stopWatchdog();
    this.emitEvent("session_cancelled", this.getSummary());
  }

  snapshot(): SessionSnapshot {
    const agents: AgentStatus[] = [];
    for (const [agentId, meta] of this.agentMap) {
      agents.push({
        agentId,
        taskId: meta.taskId,
        state: AgentState.RUNNING,
        category: meta.category,
        prompt: meta.prompt.slice(0, 120),
        startedAt: meta.startedAt,
        elapsedMs: this.now().getTime() - new Date(meta.startedAt).getTime(),
      });
    }

    const results = [...this.taskResults.values()];
    return {
      sessionId: this.sessionId,
      mode: this.mode,
      status: this.status,
      startedAt: this.startedAt,
      elapsedMs: this.startMs > 0 ? this.now().getTime() - this.startMs : 0,
      agents,
      tasksTotal: this.taskResults.size + this.agentMap.size,
      tasksCompleted: results.filter((r) => r.status === "fulfilled").length,
      tasksFailed: results.filter((r) => r.status === "rejected").length,
      tasksSkipped: results.filter((r) => r.status === "skipped").length,
      budgetPressure: {
        tokens: this.budget.pressure("tokens"),
        wall_time_ms: this.budget.pressure("wall_time_ms"),
        memory_mb: this.budget.pressure("memory_mb"),
      },
      events: this.events.slice(-50),
    };
  }

  getStatus(): SessionStatus {
    return this.status;
  }

  acquireLock(
    resourceId: string,
    holderId: string,
    priority: ResourceLockPriority = "medium",
  ): boolean {
    const result = this.lockManager.tryAcquire(resourceId, holderId, priority);
    if (result.acquired) {
      this.emitEvent("lock_acquired", { resourceId, holderId, priority });
    }
    return result.acquired;
  }

  releaseLock(resourceId: string, holderId: string): boolean {
    const released = this.lockManager.release(resourceId, holderId);
    if (released) {
      this.emitEvent("lock_released", { resourceId, holderId });
    }
    return released;
  }

  private async executeTask(
    task: OrchestrationTask,
    category: string,
  ): Promise<AgentRunResult> {
    const budgetCheck = this.budget.check();
    if (budgetCheck.exceeded) {
      throw new Error(
        `Budget exceeded on dimensions: ${budgetCheck.dimensions.join(", ")}`,
      );
    }

    this.emitEvent("agent_spawning", {
      taskId: task.id,
      category,
      prompt: task.prompt.slice(0, 120),
    });

    const agentId = await this.agentManager.spawnAgent({
      name: task.id,
      category,
      prompt: task.prompt,
      skills: [...task.skills],
      timeout: Math.ceil(task.timeout_ms / 1_000),
      maxRetries: 0,
    });

    const startTime = this.now().toISOString();
    this.agentMap.set(agentId, {
      taskId: task.id,
      category,
      prompt: task.prompt,
      startedAt: startTime,
    });
    this.watchdog.heartbeat(agentId);

    this.emitEvent("agent_spawned", {
      taskId: task.id,
      agentId,
      category,
    });

    const result = await this.waitForAgent(agentId, task);
    this.agentMap.delete(agentId);

    this.emitEvent("agent_completed", {
      taskId: task.id,
      agentId,
      returnCode: result.returnCode,
      elapsedSeconds: result.elapsedSeconds,
      stdoutLength: result.stdout.length,
      stderrLength: result.stderr.length,
    });

    this.budget.record("wall_time_ms", result.elapsedSeconds * 1_000);

    if (result.returnCode !== 0) {
      throw new Error(
        `Agent ${task.id} failed with exit code ${result.returnCode}: ${result.stderr.slice(0, 500)}`,
      );
    }

    return result;
  }

  private async waitForAgent(
    agentId: string,
    task: OrchestrationTask,
  ): Promise<AgentRunResult> {
    const deadline = this.now().getTime() + task.timeout_ms;
    const pollInterval = 500;

    while (this.now().getTime() < deadline) {
      const state = await this.agentManager.getState(agentId);
      this.watchdog.heartbeat(agentId);

      if (
        state === AgentState.COMPLETED ||
        state === AgentState.FAILED ||
        state === AgentState.CANCELLED
      ) {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return {
          returnCode: state === AgentState.COMPLETED ? 0 : 1,
          stdout: "",
          stderr: state === AgentState.FAILED ? `Agent ${task.id} failed` : "",
          elapsedSeconds:
            (this.now().getTime() -
              new Date(
                this.agentMap.get(agentId)?.startedAt ?? this.startedAt,
              ).getTime()) /
            1_000,
        };
      }

      await new Promise((resolve) => setTimeout(resolve, pollInterval));
    }

    await this.agentManager.cancelAgent(agentId);
    throw new Error(`Agent ${task.id} timed out after ${task.timeout_ms}ms`);
  }

  private startWatchdog(): void {
    if (this.watchdogInterval) return;
    this.watchdogInterval = setInterval(
      () => {
        for (const [agentId, meta] of this.agentMap) {
          if (this.watchdog.detectStall(agentId, this.watchdogThresholdMs)) {
            this.emitEvent("agent_stalled", {
              agentId,
              taskId: meta.taskId,
              thresholdMs: this.watchdogThresholdMs,
            });
          }
        }
      },
      Math.max(5_000, this.watchdogThresholdMs / 3),
    );
  }

  private stopWatchdog(): void {
    if (this.watchdogInterval) {
      clearInterval(this.watchdogInterval);
      this.watchdogInterval = null;
    }
  }

  private emitEvent(type: string, payload: Record<string, unknown>): void {
    const event: SessionEvent = {
      type,
      timestamp: this.now().toISOString(),
      sessionId: this.sessionId,
      payload,
    };

    this.events.push(event);
    if (this.events.length > this.maxEvents) {
      this.events.splice(0, this.events.length - this.maxEvents);
    }

    this.emit(type, event);
    this.emit("event", event);
  }

  private getSummary(): Record<string, unknown> {
    const results = [...this.taskResults.values()];
    return {
      sessionId: this.sessionId,
      mode: this.mode,
      tasksTotal: results.length,
      tasksCompleted: results.filter((r) => r.status === "fulfilled").length,
      tasksFailed: results.filter((r) => r.status === "rejected").length,
      tasksSkipped: results.filter((r) => r.status === "skipped").length,
      elapsedMs: this.startMs > 0 ? this.now().getTime() - this.startMs : 0,
      budget: this.budget.toSnapshot(),
    };
  }
}
