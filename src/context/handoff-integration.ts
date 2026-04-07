import {
  type AgentCard,
  buildHandoffContext,
  executeHandoff,
  type HandoffResult,
} from "../orchestration/a2a.js";
import {
  type CompactCanonicalState,
  measureRetentionQuality,
  serializeState,
} from "./workspace-reconstruction.js";
import { CheckpointSystem } from "./checkpoint.js";
import { applyLevel1Compression } from "./compression.js";

export interface HandoffPlan {
  readonly from_agent_id: string;
  readonly to_agent: AgentCard;
  readonly state: CompactCanonicalState;
  readonly project_dir: string;
}

export interface HandoffOutcome {
  readonly result: HandoffResult;
  readonly retention_quality: ReturnType<typeof measureRetentionQuality>;
  readonly checkpoint_created: boolean;
  readonly pre_handoff_checkpoint_id: string | null;
}

export interface HandoffHealthMetrics {
  readonly success: boolean;
  readonly attemptCount: number;
  readonly maxRetries: number;
  readonly tokenWaste: number;
  readonly successRate: number;
}

export const MIN_HANDOFF_RETENTION = 0.8;
export const MIN_CASCADING_RETENTION = 0.6;
export const DEFAULT_MAX_RETRIES = 3;

export function executeContextHandoff(plan: HandoffPlan): HandoffOutcome {
  const checkpointSystem = new CheckpointSystem(plan.project_dir);
  const checkpointResult = checkpointSystem.saveCheckpoint();

  serializeState(plan.state, plan.project_dir);

  const handoffContext = buildHandoffContext(plan.state, plan.to_agent);
  const handoffResult = executeHandoff(
    plan.from_agent_id,
    plan.to_agent.agent_id,
    handoffContext,
  );

  const reconstructedState: CompactCanonicalState = {
    ...plan.state,
    reconstructed_at: new Date().toISOString(),
    context_version: plan.state.context_version + 1,
  };

  const retention_quality = measureRetentionQuality(
    plan.state,
    reconstructedState,
  );

  return {
    result: handoffResult,
    retention_quality,
    checkpoint_created: true,
    pre_handoff_checkpoint_id: checkpointResult.checkpoint_id,
  };
}

export function compactContextForRetry(
  state: CompactCanonicalState,
): CompactCanonicalState {
  const estimatedTokens = JSON.stringify(state).length;
  const compressed = applyLevel1Compression(estimatedTokens);
  return {
    ...state,
    context_version: state.context_version + 1,
    reconstructed_at: new Date().toISOString(),
    _compacted_tokens: compressed.compressed_tokens,
  } as CompactCanonicalState;
}

export function executeHandoffWithRetries(
  plan: HandoffPlan,
  maxRetries: number = DEFAULT_MAX_RETRIES,
): { outcome: HandoffOutcome; health: HandoffHealthMetrics } {
  let attemptCount = 0;
  const tokenCosts: number[] = [];
  let currentState = plan.state;
  let lastOutcome: HandoffOutcome | undefined;

  while (attemptCount < maxRetries) {
    attemptCount++;
    const estimatedCost = JSON.stringify(currentState).length;
    tokenCosts.push(estimatedCost);

    lastOutcome = executeContextHandoff({
      ...plan,
      state: currentState,
    });

    if (lastOutcome.result.success) {
      const totalTokens = tokenCosts.reduce((a, b) => a + b, 0);
      const wastedTokens = totalTokens - tokenCosts[tokenCosts.length - 1]!;
      return {
        outcome: lastOutcome,
        health: {
          success: true,
          attemptCount,
          maxRetries,
          tokenWaste: wastedTokens,
          successRate: 1.0 / attemptCount,
        },
      };
    }

    currentState = compactContextForRetry(currentState);
  }

  const totalTokens = tokenCosts.reduce((a, b) => a + b, 0);
  return {
    outcome: lastOutcome!,
    health: {
      success: false,
      attemptCount,
      maxRetries,
      tokenWaste: totalTokens,
      successRate: 0,
    },
  };
}

export function getHandoffHealth(
  attemptCount: number,
  maxRetries: number,
  tokenCosts: readonly number[],
  success: boolean,
): HandoffHealthMetrics {
  const totalTokens = tokenCosts.reduce((a, b) => a + b, 0);
  const wastedTokens = success
    ? totalTokens - (tokenCosts[tokenCosts.length - 1] ?? 0)
    : totalTokens;
  return {
    success,
    attemptCount,
    maxRetries,
    tokenWaste: wastedTokens,
    successRate: success && attemptCount > 0 ? 1.0 / attemptCount : 0,
  };
}

export interface CascadingHandoffStep {
  readonly to_agent: AgentCard;
  readonly outcome: HandoffOutcome;
}

export function executeCascadingHandoff(
  initialState: CompactCanonicalState,
  agentChain: readonly AgentCard[],
  fromAgentId: string,
  projectDir: string,
): { steps: CascadingHandoffStep[]; final_retention: number } {
  if (agentChain.length === 0) {
    return { steps: [], final_retention: 1.0 };
  }

  const steps: CascadingHandoffStep[] = [];
  let currentState = initialState;
  let currentFromId = fromAgentId;

  for (const toAgent of agentChain) {
    const outcome = executeContextHandoff({
      from_agent_id: currentFromId,
      to_agent: toAgent,
      state: currentState,
      project_dir: projectDir,
    });

    steps.push({ to_agent: toAgent, outcome });

    if (!outcome.result.success) {
      break;
    }

    currentState = {
      ...currentState,
      context_version: currentState.context_version + 1,
      reconstructed_at: new Date().toISOString(),
    };
    currentFromId = toAgent.agent_id;
  }

  const successfulSteps = steps.filter((s) => s.outcome.result.success);
  const final_retention =
    successfulSteps.length === 0
      ? 0
      : successfulSteps.reduce(
          (r, s) => r * s.outcome.result.retention_rate,
          1.0,
        );

  return { steps, final_retention };
}
