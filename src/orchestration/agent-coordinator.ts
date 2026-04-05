import {
  AgentManager,
  AgentState,
  type AgentRunResult,
} from "./agent-manager.js";
import { WorkerWatchdog } from "./watchdog.js";
import type { BudgetTracker } from "./budget-tracker.js";

export interface AgentTaskSpec {
  readonly id: string;
  readonly prompt: string;
  readonly skills: readonly string[];
  readonly timeout_ms: number;
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

type ActiveAgentMeta = {
  taskId: string;
  category: string;
  prompt: string;
  startedAt: string;
};

export class AgentCoordinator {
  private readonly agentManager: AgentManager;
  private readonly watchdog: WorkerWatchdog;
  private readonly now: () => Date;
  private readonly watchdogThresholdMs: number;
  private readonly agentMap = new Map<string, ActiveAgentMeta>();
  private watchdogInterval: ReturnType<typeof setInterval> | null = null;

  constructor(params: {
    readonly agentManager: AgentManager;
    readonly watchdog: WorkerWatchdog;
    readonly now: () => Date;
    readonly watchdogThresholdMs: number;
  }) {
    this.agentManager = params.agentManager;
    this.watchdog = params.watchdog;
    this.now = params.now;
    this.watchdogThresholdMs = params.watchdogThresholdMs;
  }

  startWatchdog(
    onStalled: (data: {
      agentId: string;
      taskId: string;
      thresholdMs: number;
    }) => void,
  ): void {
    if (this.watchdogInterval) return;
    this.watchdogInterval = setInterval(
      () => {
        for (const [agentId, meta] of this.agentMap) {
          if (this.watchdog.detectStall(agentId, this.watchdogThresholdMs)) {
            onStalled({
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

  stopWatchdog(): void {
    if (this.watchdogInterval) {
      clearInterval(this.watchdogInterval);
      this.watchdogInterval = null;
    }
  }

  async cancelAll(): Promise<void> {
    for (const [agentId] of this.agentMap) {
      await this.agentManager.cancelAgent(agentId);
    }
  }

  snapshotAgents(): AgentStatus[] {
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
    return agents;
  }

  activeCount(): number {
    return this.agentMap.size;
  }

  async executeTask(
    task: AgentTaskSpec,
    category: string,
    budget: BudgetTracker,
    emitEvent: (type: string, payload: Record<string, unknown>) => void,
    sessionStartedAt: string,
  ): Promise<AgentRunResult> {
    const budgetCheck = budget.check();
    if (budgetCheck.exceeded) {
      throw new Error(
        `Budget exceeded on dimensions: ${budgetCheck.dimensions.join(", ")}`,
      );
    }

    emitEvent("agent_spawning", {
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

    emitEvent("agent_spawned", {
      taskId: task.id,
      agentId,
      category,
    });

    const result = await this.waitForAgent(agentId, task, sessionStartedAt);
    this.agentMap.delete(agentId);

    emitEvent("agent_completed", {
      taskId: task.id,
      agentId,
      returnCode: result.returnCode,
      elapsedSeconds: result.elapsedSeconds,
      stdoutLength: result.stdout.length,
      stderrLength: result.stderr.length,
    });

    budget.recordWallTime(result.elapsedSeconds * 1_000);

    if (result.returnCode !== 0) {
      throw new Error(
        `Agent ${task.id} failed with exit code ${result.returnCode}: ${result.stderr.slice(0, 500)}`,
      );
    }

    return result;
  }

  private async waitForAgent(
    agentId: string,
    task: AgentTaskSpec,
    sessionStartedAt: string,
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
                this.agentMap.get(agentId)?.startedAt ?? sessionStartedAt,
              ).getTime()) /
            1_000,
        };
      }

      await new Promise((resolve) => setTimeout(resolve, pollInterval));
    }

    await this.agentManager.cancelAgent(agentId);
    throw new Error(`Agent ${task.id} timed out after ${task.timeout_ms}ms`);
  }
}

export { AgentManager, AgentState, type AgentRunResult };
