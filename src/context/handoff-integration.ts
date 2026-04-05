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

export const MIN_HANDOFF_RETENTION = 0.8;
export const MIN_CASCADING_RETENTION = 0.6;

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
