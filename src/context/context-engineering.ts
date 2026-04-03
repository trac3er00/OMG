import {
  type ContextState,
  selectStrategy,
  type StrategySelectionResult,
} from "./strategy-router.js";
import {
  type CompactCanonicalState,
  serializeState,
  deserializeState,
  measureRetentionQuality,
} from "./workspace-reconstruction.js";
import { CheckpointSystem } from "./checkpoint.js";
import {
  compress,
  type CompressionResult,
  classifyPressureLevel,
  type PressureResponse,
} from "./compression.js";
import {
  type AgentCard,
  buildHandoffContext,
  executeHandoff,
  type HandoffResult,
} from "../orchestration/a2a.js";

export interface ContextMetrics {
  readonly pressure: number;
  readonly pressure_level: PressureResponse["level"];
  readonly retention_rate: number;
  readonly checkpoint_count: number;
  readonly last_strategy: StrategySelectionResult | null;
}

export class ContextEngineeringSystem {
  private readonly checkpointSystem: CheckpointSystem;
  private lastStrategy: StrategySelectionResult | null = null;
  private checkpointCount = 0;

  constructor(
    private readonly projectDir: string,
    checkpointInterval = 50,
  ) {
    this.checkpointSystem = new CheckpointSystem(
      projectDir,
      checkpointInterval,
    );
  }

  compress(state: ContextState): CompressionResult {
    const result = compress(state);
    this.lastStrategy = selectStrategy(state);
    return result;
  }

  evaluate(state: ContextState): StrategySelectionResult | null {
    const result = selectStrategy(state);
    this.lastStrategy = result;
    return result;
  }

  reconstruct(state: CompactCanonicalState): void {
    serializeState(state, this.projectDir);
  }

  checkpoint(): ReturnType<CheckpointSystem["saveCheckpoint"]> {
    this.checkpointCount++;
    return this.checkpointSystem.saveCheckpoint();
  }

  onToolCall(): ReturnType<CheckpointSystem["onToolCall"]> {
    return this.checkpointSystem.onToolCall();
  }

  handoff(
    state: CompactCanonicalState,
    targetAgent: AgentCard,
    fromAgentId: string,
  ): HandoffResult {
    const ctx = buildHandoffContext(state, targetAgent);
    return executeHandoff(fromAgentId, targetAgent.agent_id, ctx);
  }

  measure(state: ContextState): ContextMetrics {
    const pressure = state.totalTokens / state.maxTokens;
    const pressureResponse = classifyPressureLevel(pressure);
    const currentState = deserializeState(this.projectDir);
    const retention_rate =
      currentState != null
        ? measureRetentionQuality(currentState, {
            ...currentState,
            reconstructed_at: new Date().toISOString(),
          }).retention_rate
        : 1.0;

    return {
      pressure,
      pressure_level: pressureResponse.level,
      retention_rate,
      checkpoint_count: this.checkpointCount,
      last_strategy: this.lastStrategy,
    };
  }
}
