/**
 * Orchestration type definitions — full inventory.
 * Ported from Python TypedDict definitions in runtime/.
 */
import { z } from "zod";

// Re-export shared boundary types
export type {
  AgentConfig,
  AgentRecommendation,
  AgentState,
  BudgetEnvelope,
  IsolationMode,
  RoutingSignals,
  TaskComplexity,
  TeamDispatchRequest,
  TeamDispatchResult,
  WorkerTask,
} from "../interfaces/orchestration.js";

// ---------------------------------------------------------------------------
// Forge stage ordering (forge_contracts.py)
// ---------------------------------------------------------------------------

export const ForgeStageSchema = z.enum([
  "data_prepare",
  "synthetic_refine",
  "train_distill",
  "evaluate",
  "regression_test",
]);
export type ForgeStage = z.infer<typeof ForgeStageSchema>;

// ---------------------------------------------------------------------------
// Forge job
// ---------------------------------------------------------------------------

export const ForgeJobSchema = z.object({
  job_id: z.string(),
  domain: z.string(),
  operation: z.string(),
  intent: z.string().optional(),
  adapter: z.string().optional(),
  run_id: z.string(),
  project_dir: z.string(),
  created_at: z.string(),
});
export type ForgeJob = z.infer<typeof ForgeJobSchema>;

// ---------------------------------------------------------------------------
// Worker heartbeat (worker_watchdog.py)
// ---------------------------------------------------------------------------

export const WorkerHeartbeatSchema = z.object({
  run_id: z.string(),
  pid: z.number().int().optional(),
  last_activity: z.string(),
  status: z.string(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});
export type WorkerHeartbeat = z.infer<typeof WorkerHeartbeatSchema>;

// ---------------------------------------------------------------------------
// Job record (subagent_dispatcher.py)
// ---------------------------------------------------------------------------

export const JobStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "cancelled",
]);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const JobRecordSchema = z.object({
  job_id: z.string(),
  status: JobStatusSchema,
  isolation_mode: z.string(),
  created_at: z.string(),
  started_at: z.string().optional(),
  completed_at: z.string().optional(),
  exit_code: z.number().int().optional(),
  artifacts_path: z.string().optional(),
  error: z.string().optional(),
});
export type JobRecord = z.infer<typeof JobRecordSchema>;

// ---------------------------------------------------------------------------
// Team dispatch target
// ---------------------------------------------------------------------------

export const TeamDispatchTargetSchema = z.enum([
  "codex",
  "gemini",
  "ccg",
  "claude",
  "auto",
]);
export type TeamDispatchTarget = z.infer<typeof TeamDispatchTargetSchema>;

// ---------------------------------------------------------------------------
// Decision context (decision_engine.py)
// ---------------------------------------------------------------------------

export const DecisionContextSchema = z.object({
  prompt: z.string(),
  project_dir: z.string(),
  domain_hints: z.array(z.string()),
  intent: z.string().optional(),
});
export type DecisionContext = z.infer<typeof DecisionContextSchema>;

// ---------------------------------------------------------------------------
// Install planner (install_planner.py)
// ---------------------------------------------------------------------------

export const InstallActionKindSchema = z.enum([
  "write_mcp_config",
  "write_settings",
  "write_cli_config",
]);
export type InstallActionKind = z.infer<typeof InstallActionKindSchema>;

export const InstallResultSchema = z.object({
  executed: z.boolean(),
  actions_completed: z.array(z.string()),
  actions_skipped: z.array(z.string()),
  receipt: z.unknown(),
  errors: z.array(z.string()),
});
export type InstallResult = z.infer<typeof InstallResultSchema>;

// ---------------------------------------------------------------------------
// Subscription tiers (subscription_tiers.py)
// ---------------------------------------------------------------------------

export const TierSpecSchema = z.object({
  budget_usd_per_session: z.number(),
  max_parallel_agents: z.number().int(),
  features: z.array(z.string()),
});
export type TierSpec = z.infer<typeof TierSpecSchema>;

export const TierDetectionResultSchema = z.object({
  tier: z.string(),
  provenance: z.string(),
  confidence: z.number().min(0).max(1),
  budget_usd_per_session: z.number(),
  max_parallel_agents: z.number().int(),
  reason: z.string().optional(),
});
export type TierDetectionResult = z.infer<typeof TierDetectionResultSchema>;

// ---------------------------------------------------------------------------
// Router executor (router_executor.py → WorkerTask Python shape)
// ---------------------------------------------------------------------------

export const WorkerTaskPySchema = z.object({
  agent_name: z.string().optional(),
  prompt: z.string().optional(),
  order: z.number().int().optional(),
});
export type WorkerTaskPy = z.infer<typeof WorkerTaskPySchema>;

// ---------------------------------------------------------------------------
// Agent config Zod schema (matches interfaces/orchestration.ts)
// ---------------------------------------------------------------------------

export const AgentConfigSchema = z.object({
  name: z.string(),
  category: z.string(),
  prompt: z.string(),
  skills: z.array(z.string()),
  timeout: z.number(),
  maxRetries: z.number().int(),
  subagentType: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Budget envelope Zod schema (matches interfaces/orchestration.ts)
// ---------------------------------------------------------------------------

export const BudgetEnvelopeSchema = z.object({
  runId: z.string(),
  cpuSecondsLimit: z.number(),
  memoryMbLimit: z.number(),
  wallTimeSecondsLimit: z.number(),
  tokenLimit: z.number(),
  networkBytesLimit: z.number(),
  cpuSecondsUsed: z.number(),
  memoryMbPeak: z.number(),
  wallTimeSecondsUsed: z.number(),
  tokensUsed: z.number(),
  networkBytesUsed: z.number(),
  exceeded: z.boolean(),
  exceededDimensions: z.array(z.string()),
});
