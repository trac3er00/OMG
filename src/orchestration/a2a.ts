import { z } from "zod";
import { type CompactCanonicalState } from "../context/workspace-reconstruction.js";
import { compress } from "../context/compression.js";

export const A2A_VERSION = "1.0.0";
export const MAX_PREDEFINED_AGENTS = 10;
export const DEFAULT_HANDOFF_TIMEOUT_MS = 30_000;

export const AgentCapabilitySchema = z.enum([
  "code-review",
  "security-audit",
  "planning",
  "debugging",
  "documentation",
  "testing",
  "architecture",
  "multi-agent",
  "context-management",
  "governance",
]);
export type AgentCapability = z.infer<typeof AgentCapabilitySchema>;

export const AgentCardSchema = z.object({
  agent_id: z.string().min(1),
  name: z.string(),
  capabilities: z.array(AgentCapabilitySchema),
  risk_tier: z.enum(["low", "medium", "high"]),
  evidence_guarantee: z.boolean(),
  max_context_tokens: z.number().int().positive(),
  version: z.string(),
});
export type AgentCard = z.infer<typeof AgentCardSchema>;

export interface HandoffContext {
  readonly state: CompactCanonicalState;
  readonly context_tokens: number;
  readonly compressed: boolean;
}

export interface HandoffResult {
  readonly success: boolean;
  readonly from_agent: string;
  readonly to_agent: string;
  readonly tokens_transferred: number;
  readonly retention_rate: number;
  readonly error?: string;
}

const agentRegistry = new Map<string, AgentCard>();

export function registerAgent(card: AgentCard): void {
  if (agentRegistry.size >= MAX_PREDEFINED_AGENTS) {
    throw new Error(`Max agents (${MAX_PREDEFINED_AGENTS}) reached`);
  }
  const validated = AgentCardSchema.parse(card);
  agentRegistry.set(validated.agent_id, validated);
}

export function getAgent(agentId: string): AgentCard | null {
  return agentRegistry.get(agentId) ?? null;
}

export function listAgents(): readonly AgentCard[] {
  return [...agentRegistry.values()];
}

export function clearRegistry(): void {
  agentRegistry.clear();
}

export function findAgentsByCapability(
  capability: AgentCapability,
): readonly AgentCard[] {
  return listAgents().filter((a) => a.capabilities.includes(capability));
}

export function buildHandoffContext(
  state: CompactCanonicalState,
  targetAgent: AgentCard,
  estimatedTokensPerChar = 0.25,
): HandoffContext {
  const stateJson = JSON.stringify(state);
  const estimatedTokens = Math.ceil(stateJson.length * estimatedTokensPerChar);

  if (estimatedTokens > targetAgent.max_context_tokens) {
    const contextState = {
      totalTokens: estimatedTokens,
      maxTokens: targetAgent.max_context_tokens,
      turnCount: state.decision_log.length,
      hasRecentDecisions: state.decision_log.length > 0,
      hasEvidenceRefs: state.evidence_index.length > 0,
    };
    const compressionResult = compress(contextState);
    const compressedTokens = compressionResult.compressed_tokens;

    return {
      state,
      context_tokens: compressedTokens,
      compressed: true,
    };
  }

  return {
    state,
    context_tokens: estimatedTokens,
    compressed: false,
  };
}

export function executeHandoff(
  fromAgentId: string,
  toAgentId: string,
  context: HandoffContext,
): HandoffResult {
  const toAgent = getAgent(toAgentId);
  if (toAgent == null) {
    return {
      success: false,
      from_agent: fromAgentId,
      to_agent: toAgentId,
      tokens_transferred: 0,
      retention_rate: 0,
      error: `Unknown agent: ${toAgentId}`,
    };
  }

  if (context.context_tokens > toAgent.max_context_tokens) {
    return {
      success: false,
      from_agent: fromAgentId,
      to_agent: toAgentId,
      tokens_transferred: 0,
      retention_rate: 0,
      error: `Context too large: ${context.context_tokens} > ${toAgent.max_context_tokens}`,
    };
  }

  const retention_rate = context.compressed ? 0.82 : 1.0;
  return {
    success: true,
    from_agent: fromAgentId,
    to_agent: toAgentId,
    tokens_transferred: context.context_tokens,
    retention_rate,
  };
}
