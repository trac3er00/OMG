import { EventEmitter } from "node:events";
import { z } from "zod";
import {
  AgentCoordinator,
  AgentManager,
  type AgentStatus,
} from "./agent-coordinator.js";
import {
  ExecutionController,
  type OrchestrationMode,
  type SessionStatus,
} from "./execution-controller.js";
import {
  BudgetTracker,
  DEFAULT_BUDGET,
  type BudgetLimits,
} from "./budget-tracker.js";
import {
  emitSessionEvent,
  latestSessionEvents,
  type SessionEvent,
} from "./session-events.js";
import { WorkerWatchdog } from "./watchdog.js";
import { ResourceLockManager, type ResourceLockPriority } from "./deadlock.js";
import { type DagTaskResult } from "./dag-executor.js";
import {
  detectContextDecay,
  reconstructWorkspace,
  createCompactState,
  getWorkspaceDurabilityState,
  type ContextFreshnessInput,
  type FileReference,
} from "../context/workspace-reconstruction.js";

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

export interface DurabilityMetrics {
  totalReconstructions: number;
  averageFreshnessScore: number;
  decayEventCount: number;
  lastReconstructionAt?: string;
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
  readonly durabilityMetrics: Readonly<DurabilityMetrics>;
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
  readonly freshnessCheckIntervalMinutes?: number;
  readonly freshnessThreshold?: number;
}

const DEFAULT_WATCHDOG_THRESHOLD_MS = 60_000;
const MAX_EVENTS = 500;
export const CHECK_INTERVAL_MINUTES = 10;
export const DEFAULT_FRESHNESS_THRESHOLD = 40;

export class OrchestrationSession extends EventEmitter {
  static create(
    options: OrchestrationSessionOptions = {},
  ): OrchestrationSession {
    return new OrchestrationSession(options);
  }

  readonly sessionId: string;
  readonly mode: OrchestrationMode;

  private status: SessionStatus = "idle";
  private startedAt = "";
  private startMs = 0;

  private readonly lockManager: ResourceLockManager;
  private readonly now: () => Date;
  private readonly maxEvents: number;
  private readonly budget: BudgetTracker;
  private readonly execution: ExecutionController;
  private readonly agents: AgentCoordinator;
  private readonly taskResults = new Map<string, DagTaskResult>();
  private readonly events: SessionEvent[] = [];

  private freshnessCheckTimer: ReturnType<typeof setInterval> | null = null;
  private readonly fileReferences: FileReference[] = [];
  private readonly freshnessScores: number[] = [];
  private readonly freshnessCheckIntervalMs: number;
  private readonly freshnessThreshold: number;
  private readonly projectDir: string;
  private readonly createdAt: string;
  private readonly durability: DurabilityMetrics = {
    totalReconstructions: 0,
    averageFreshnessScore: 100,
    decayEventCount: 0,
  };

  constructor(options: OrchestrationSessionOptions = {}) {
    super();

    this.now = options.now ?? (() => new Date());
    const idGen =
      options.idGenerator ?? (() => `orch-${crypto.randomUUID().slice(0, 12)}`);
    this.sessionId = idGen();
    this.mode = options.mode ?? "ultrawork";
    this.maxEvents = options.maxEvents ?? MAX_EVENTS;

    const watchdogThresholdMs =
      options.watchdogThresholdMs ?? DEFAULT_WATCHDOG_THRESHOLD_MS;

    const projectDir = options.projectDir ?? process.cwd();
    this.projectDir = projectDir;
    this.createdAt = this.now().toISOString();
    this.freshnessCheckIntervalMs =
      (options.freshnessCheckIntervalMinutes ?? CHECK_INTERVAL_MINUTES) *
      60_000;
    this.freshnessThreshold =
      options.freshnessThreshold ?? DEFAULT_FRESHNESS_THRESHOLD;

    const agentManager = AgentManager.create({
      projectDir,
      now: this.now,
    });

    this.execution = new ExecutionController(this.mode, options.concurrency);
    this.budget = new BudgetTracker(
      this.sessionId,
      options.budgetLimits ?? DEFAULT_BUDGET,
    );

    this.agents = new AgentCoordinator({
      agentManager,
      watchdog: WorkerWatchdog.create({ now: () => this.now().getTime() }),
      now: this.now,
      watchdogThresholdMs,
    });

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
      concurrency: this.execution.concurrency,
    });

    this.agents.startWatchdog((payload) =>
      this.emitEvent("agent_stalled", payload),
    );
    this.startFreshnessChecking();

    try {
      for (const task of tasks) {
        const validated = OrchestrationTaskSchema.parse(task);
        const registration = this.execution.registerTask(
          validated,
          (work, category) =>
            this.agents.executeTask(
              work,
              category,
              this.budget,
              (type, payload) => this.emitEvent(type, payload),
              this.startedAt,
            ),
        );

        this.emitEvent("task_registered", {
          taskId: registration.taskId,
          category: registration.category,
          complexity: registration.complexity,
          deps: registration.deps,
          provider: registration.provider,
          reasoning: registration.reasoning,
        });
      }

      for await (const result of this.execution.execute()) {
        this.taskResults.set(result.id, result);
        this.budget.recordWallTime(this.now().getTime() - this.startMs);

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
      this.agents.stopWatchdog();
      this.stopFreshnessChecking();
    }
  }

  async cancel(): Promise<void> {
    if (this.status !== "running") return;

    this.status = "cancelled";
    await this.agents.cancelAll();
    this.agents.stopWatchdog();
    this.stopFreshnessChecking();
    this.emitEvent("session_cancelled", this.getSummary());
  }

  snapshot(): SessionSnapshot {
    const results = [...this.taskResults.values()];
    return {
      sessionId: this.sessionId,
      mode: this.mode,
      status: this.status,
      startedAt: this.startedAt,
      elapsedMs: this.startMs > 0 ? this.now().getTime() - this.startMs : 0,
      agents: this.agents.snapshotAgents(),
      tasksTotal: this.taskResults.size + this.agents.activeCount(),
      tasksCompleted: results.filter((r) => r.status === "fulfilled").length,
      tasksFailed: results.filter((r) => r.status === "rejected").length,
      tasksSkipped: results.filter((r) => r.status === "skipped").length,
      budgetPressure: this.budget.pressureSnapshot(),
      events: latestSessionEvents(this.events, 50),
      durabilityMetrics: this.getDurabilityMetrics(),
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

  recordFileReference(path: string): void {
    this.fileReferences.push({
      path,
      referencedAt: this.now().toISOString(),
    });
  }

  async checkFreshness(): Promise<number> {
    const sessionStart = this.startedAt || this.createdAt;
    const input: ContextFreshnessInput = {
      fileReferences: this.fileReferences,
      sessionStartedAt: sessionStart,
      now: this.now(),
    };

    const result = detectContextDecay(input, this.freshnessThreshold / 100);
    this.freshnessScores.push(result.freshnessScore);

    if (result.decayDetected) {
      this.durability.decayEventCount++;
      this.emitEvent("context-decay-detected", {
        freshnessScore: result.freshnessScore,
        threshold: this.freshnessThreshold,
        efficiencyRatio: result.efficiencyRatio,
        fileReferenceCount: this.fileReferences.length,
      });
      await this.attemptReconstruction(result.freshnessScore);
    }

    this.updateAverageFreshness();
    return result.freshnessScore;
  }

  getDurabilityMetrics(): Readonly<DurabilityMetrics> {
    return { ...this.durability };
  }

  getContextFreshnessScore(): number {
    if (this.freshnessScores.length > 0) {
      return this.freshnessScores[this.freshnessScores.length - 1]!;
    }
    return getWorkspaceDurabilityState().contextFreshnessScore;
  }

  private startFreshnessChecking(): void {
    if (this.freshnessCheckTimer !== null) return;
    this.freshnessCheckTimer = setInterval(() => {
      void this.checkFreshness();
    }, this.freshnessCheckIntervalMs);
  }

  private stopFreshnessChecking(): void {
    if (this.freshnessCheckTimer !== null) {
      clearInterval(this.freshnessCheckTimer);
      this.freshnessCheckTimer = null;
    }
  }

  private async attemptReconstruction(freshnessScore: number): Promise<void> {
    try {
      const state = createCompactState("session-workspace-reconstruction", {
        contextFreshnessScore: freshnessScore,
      });

      await reconstructWorkspace({
        projectDir: this.projectDir,
        state,
        fileReferences: this.fileReferences,
        sessionStartedAt: this.startedAt || this.createdAt,
        now: this.now(),
      });

      this.durability.totalReconstructions++;
      this.durability.lastReconstructionAt = this.now().toISOString();

      this.emitEvent("workspace_reconstructed", {
        freshnessScore,
        totalReconstructions: this.durability.totalReconstructions,
      });
    } catch {
      this.emitEvent("reconstruction_failed", {
        freshnessScore,
      });
    }
  }

  private updateAverageFreshness(): void {
    if (this.freshnessScores.length === 0) return;
    const sum = this.freshnessScores.reduce((a, b) => a + b, 0);
    this.durability.averageFreshnessScore = Math.round(
      sum / this.freshnessScores.length,
    );
  }

  private emitEvent(type: string, payload: Record<string, unknown>): void {
    emitSessionEvent({
      emitter: this,
      type,
      payload,
      sessionId: this.sessionId,
      now: this.now,
      events: this.events,
      maxEvents: this.maxEvents,
    });
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
      durabilityMetrics: this.getDurabilityMetrics(),
    };
  }
}
