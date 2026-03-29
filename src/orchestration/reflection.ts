export interface ReflectionCheckpoint<State> {
  readonly id: string;
  readonly createdAt: string;
  readonly state: State;
}

export interface ReflectionEvaluation {
  readonly verdict: "pass" | "warn" | "fail";
  readonly summary: string;
  readonly completedSteps: number;
  readonly totalSteps: number;
  readonly rollbackCount: number;
}

export interface ReflectionStepResult<State> {
  readonly checkpointId: string;
  readonly status: "completed" | "failed";
  readonly state: State;
  readonly error?: string;
}

export interface ReflectionRollbackResult<State> {
  readonly checkpointId: string;
  readonly state: State;
}

export interface ReflectionPlanStep<State> {
  readonly id: string;
  readonly description: string;
  readonly run: (state: State) => State | Promise<State>;
}

export interface ReflectionPlanContext<State> {
  readonly task: string;
  readonly status: "completed" | "rolled_back";
  readonly completedSteps: readonly string[];
  readonly totalSteps: number;
  readonly rollbackCount: number;
  readonly state: State;
  readonly failedStepId?: string;
}

export interface ReflectionPlanResult<State> {
  readonly status: "completed" | "rolled_back";
  readonly completedSteps: readonly string[];
  readonly state: State;
  readonly evaluation: ReflectionEvaluation;
  readonly failedStepId?: string;
  readonly rollbackCheckpointId?: string;
  readonly error?: string;
}

export interface ReflectionEngineOptions<State> {
  readonly initialState: State;
  readonly idGenerator?: () => string;
  readonly now?: () => Date;
  readonly cloneState?: (state: State) => State;
  readonly evaluateTask?: (context: ReflectionPlanContext<State>) => ReflectionEvaluation;
}

function defaultIdGenerator(): string {
  return `checkpoint-${crypto.randomUUID()}`;
}

function defaultCloneState<State>(state: State): State {
  return structuredClone(state);
}

function formatError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function defaultEvaluation<State>(context: ReflectionPlanContext<State>): ReflectionEvaluation {
  if (context.status === "rolled_back") {
    return {
      verdict: "fail",
      summary: `Reflection halted at ${context.failedStepId ?? "unknown step"} and restored the last checkpoint.`,
      completedSteps: context.completedSteps.length,
      totalSteps: context.totalSteps,
      rollbackCount: context.rollbackCount,
    };
  }

  if (context.rollbackCount > 0) {
    return {
      verdict: "warn",
      summary: `Reflection completed ${context.completedSteps.length}/${context.totalSteps} steps after ${context.rollbackCount} rollback(s).`,
      completedSteps: context.completedSteps.length,
      totalSteps: context.totalSteps,
      rollbackCount: context.rollbackCount,
    };
  }

  return {
    verdict: "pass",
    summary: `Reflection completed ${context.completedSteps.length}/${context.totalSteps} planned steps without rollback.`,
    completedSteps: context.completedSteps.length,
    totalSteps: context.totalSteps,
    rollbackCount: context.rollbackCount,
  };
}

export class ReflectionEngine<State> {
  static create<State>(options: ReflectionEngineOptions<State>): ReflectionEngine<State> {
    return new ReflectionEngine(options);
  }

  private readonly idGenerator: () => string;

  private readonly now: () => Date;

  private readonly cloneState: (state: State) => State;

  private readonly evaluateTask: (context: ReflectionPlanContext<State>) => ReflectionEvaluation;

  private readonly checkpoints = new Map<string, ReflectionCheckpoint<State>>();

  private currentState: State;

  private rollbackCount = 0;

  private lastEvaluation?: ReflectionEvaluation;

  constructor(options: ReflectionEngineOptions<State>) {
    this.idGenerator = options.idGenerator ?? defaultIdGenerator;
    this.now = options.now ?? (() => new Date());
    this.cloneState = options.cloneState ?? defaultCloneState;
    this.evaluateTask = options.evaluateTask ?? defaultEvaluation;
    this.currentState = this.cloneState(options.initialState);
  }

  getState(): State {
    return this.cloneState(this.currentState);
  }

  getLastEvaluation(): ReflectionEvaluation | undefined {
    return this.lastEvaluation;
  }

  createCheckpoint(state: State): string {
    const checkpointId = this.idGenerator();
    this.checkpoints.set(checkpointId, {
      id: checkpointId,
      createdAt: this.now().toISOString(),
      state: this.cloneState(state),
    });
    return checkpointId;
  }

  async executeStep(step: (state: State) => State | Promise<State>): Promise<ReflectionStepResult<State>> {
    const checkpointId = this.createCheckpoint(this.currentState);
    const workingState = this.cloneState(this.currentState);
    this.currentState = workingState;

    try {
      const nextState = await step(workingState);
      this.currentState = this.cloneState(nextState);
      return {
        checkpointId,
        status: "completed",
        state: this.getState(),
      };
    } catch (error) {
      return {
        checkpointId,
        status: "failed",
        state: this.getState(),
        error: formatError(error),
      };
    }
  }

  rollback(checkpointId: string): ReflectionRollbackResult<State> {
    const checkpoint = this.checkpoints.get(checkpointId);
    if (checkpoint === undefined) {
      throw new Error(`Unknown checkpoint: ${checkpointId}`);
    }

    this.currentState = this.cloneState(checkpoint.state);
    this.rollbackCount += 1;

    return {
      checkpointId,
      state: this.getState(),
    };
  }

  async runPlan(task: string, steps: readonly ReflectionPlanStep<State>[]): Promise<ReflectionPlanResult<State>> {
    const completedSteps: string[] = [];
    const rollbackCountBeforePlan = this.rollbackCount;

    for (const step of steps) {
      const execution = await this.executeStep(step.run);
      if (execution.status === "failed") {
        const rollback = this.rollback(execution.checkpointId);
        const evaluation = this.evaluateTask({
          task,
          status: "rolled_back",
          completedSteps,
          totalSteps: steps.length,
          rollbackCount: this.rollbackCount - rollbackCountBeforePlan,
          state: rollback.state,
          failedStepId: step.id,
        });
        this.lastEvaluation = evaluation;

        if (execution.error !== undefined) {
          return {
            status: "rolled_back",
            completedSteps,
            failedStepId: step.id,
            rollbackCheckpointId: execution.checkpointId,
            error: execution.error,
            state: rollback.state,
            evaluation,
          };
        }

        return {
          status: "rolled_back",
          completedSteps,
          failedStepId: step.id,
          rollbackCheckpointId: execution.checkpointId,
          state: rollback.state,
          evaluation,
        };
      }

      completedSteps.push(step.id);
    }

    const finalState = this.getState();
    const evaluation = this.evaluateTask({
      task,
      status: "completed",
      completedSteps,
      totalSteps: steps.length,
      rollbackCount: this.rollbackCount - rollbackCountBeforePlan,
      state: finalState,
    });
    this.lastEvaluation = evaluation;

    return {
      status: "completed",
      completedSteps,
      state: finalState,
      evaluation,
    };
  }
}
