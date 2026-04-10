/**
 * Runtime module type definitions.
 * Full type inventory ported from Python TypedDict definitions in runtime/.
 */
import { z } from "zod";

// Re-export shared boundary types rather than duplicating
export type {
  AgentConfig,
  AgentState,
  BudgetEnvelope,
  IsolationMode,
  RoutingSignals,
  TaskComplexity,
  TeamDispatchRequest,
  TeamDispatchResult,
} from "../interfaces/orchestration.js";

export type {
  ContextPacket,
  DefenseState,
  ProfileDigest,
  TrustTier,
  TrustState,
} from "../interfaces/state.js";

// ---------------------------------------------------------------------------
// Schema versions (runtime_contracts.py → SchemaVersion)
// ---------------------------------------------------------------------------

export const SchemaVersionSchema = z.object({
  schema_name: z.string(),
  version: z.string(),
  required_fields: z.array(z.string()),
});
export type SchemaVersion = z.infer<typeof SchemaVersionSchema>;

// ---------------------------------------------------------------------------
// State layout (runtime_contracts.py → default_layout)
// ---------------------------------------------------------------------------

export const StateLayoutSchema = z.record(
  z.string(),
  z.record(z.string(), z.string()),
);
export type StateLayout = z.infer<typeof StateLayoutSchema>;

// ---------------------------------------------------------------------------
// Context limits (context_limits.py → ContextLimitEntry)
// ---------------------------------------------------------------------------

export const ContextLimitEntrySchema = z.object({
  context_tokens: z.number().int(),
  output_reserve_tokens: z.number().int(),
  class_label: z.string(),
  preflight_counting: z.boolean(),
  native_compaction: z.boolean(),
  compaction_trigger_default: z.number().int(),
  notes: z.string(),
});
export type ContextLimitEntry = z.infer<typeof ContextLimitEntrySchema>;

// ---------------------------------------------------------------------------
// Verdict schema (verdict_schema.py → VerdictReceipt)
// ---------------------------------------------------------------------------

export const VerdictStatusSchema = z.enum([
  "pass",
  "fail",
  "action_required",
  "pending",
]);
export type VerdictStatus = z.infer<typeof VerdictStatusSchema>;

export const VerdictReceiptSchema = z.object({
  status: VerdictStatusSchema,
  verdict: VerdictStatusSchema,
  blockers: z.array(z.string()),
  planned_actions: z.array(z.unknown()),
  executed_actions: z.array(z.unknown()),
  provenance: z.string().nullable(),
  evidence_paths: z.record(z.string(), z.string()),
  next_steps: z.array(z.string()),
  executed: z.boolean(),
  metadata: z.record(z.string(), z.unknown()),
});
export type VerdictReceipt = z.infer<typeof VerdictReceiptSchema>;

// ---------------------------------------------------------------------------
// Hook governor (hook_governor.py → ValidationResult)
// ---------------------------------------------------------------------------

export const HookValidationResultSchema = z.object({
  status: z.enum(["ok", "blocked"]),
  blockers: z.array(z.string()),
});
export type HookValidationResult = z.infer<typeof HookValidationResultSchema>;

// ---------------------------------------------------------------------------
// Runtime profile (runtime_profile.py → RuntimeProfile, CanonicalModeProfile)
// ---------------------------------------------------------------------------

export const RuntimeProfileSchema = z.object({
  profile: z.string(),
  max_workers: z.number().int(),
  background_polling: z.boolean(),
});
export type RuntimeProfile = z.infer<typeof RuntimeProfileSchema>;

export const CanonicalModeProfileSchema = z.object({
  concurrency: z.number().int(),
  background_verification: z.boolean(),
  context_window: z.string(),
  noise_level: z.string(),
});
export type CanonicalModeProfile = z.infer<typeof CanonicalModeProfileSchema>;

// ---------------------------------------------------------------------------
// Feature registry (feature_registry.py → FeatureConfig)
// ---------------------------------------------------------------------------

export const FeatureConfigSchema = z.object({
  enabled: z.boolean(),
  depends_on: z.array(z.string()),
  description: z.string(),
});
export type FeatureConfig = z.infer<typeof FeatureConfigSchema>;

// ---------------------------------------------------------------------------
// Session health
// ---------------------------------------------------------------------------

export const SessionHealthStatusSchema = z.enum([
  "healthy",
  "degraded",
  "critical",
  "unknown",
]);
export type SessionHealthStatus = z.infer<typeof SessionHealthStatusSchema>;

export const SessionHealthSchema = z.object({
  status: SessionHealthStatusSchema,
  tool_count: z.number().int(),
  risk_level: z.string(),
  warnings: z.array(z.string()),
  actions: z.array(z.string()),
  updated_at: z.string(),
});
export type SessionHealth = z.infer<typeof SessionHealthSchema>;

// ---------------------------------------------------------------------------
// Memory item (memory_parsers/claude_import.py → MemoryItem)
// ---------------------------------------------------------------------------

export const MemoryItemSchema = z.object({
  key: z.string(),
  content: z.string(),
  source_cli: z.string(),
  tags: z.array(z.string()),
});
export type MemoryItem = z.infer<typeof MemoryItemSchema>;

// ---------------------------------------------------------------------------
// Evidence narrator (evidence_narrator.py → NarrativeResult)
// ---------------------------------------------------------------------------

export const NarrativeResultSchema = z.object({
  verdict_summary: z.string(),
  blockers_section: z.array(z.string()),
  provenance_note: z.string().nullable(),
  evidence_paths_section: z.array(z.string()),
  next_actions: z.array(z.string()),
});
export type NarrativeResult = z.infer<typeof NarrativeResultSchema>;

// ---------------------------------------------------------------------------
// Kernel run (exec_kernel.py)
// ---------------------------------------------------------------------------

export const IsolationModeSchema = z.enum(["worktree", "container", "none"]);

export const KernelRunSchema = z.object({
  run_id: z.string(),
  isolation_mode: IsolationModeSchema,
  evidence_hooks: z.array(z.string()),
  attach_log: z.string(),
  started_at: z.string(),
  project_dir: z.string(),
});
export type KernelRun = z.infer<typeof KernelRunSchema>;

// ---------------------------------------------------------------------------
// JSON helpers (runtime_contracts.py)
// ---------------------------------------------------------------------------

export type JsonPrimitive = string | number | boolean | null;
export interface JsonObject {
  [key: string]: JsonValue;
}
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
