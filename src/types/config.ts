/**
 * Configuration type definitions.
 * Ported from Python shapes in runtime/ config modules.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Preset names
// ---------------------------------------------------------------------------

export const PresetNameSchema = z.enum(["safe", "balanced", "interop", "labs", "buffet", "production"]);
export type PresetName = z.infer<typeof PresetNameSchema>;

// ---------------------------------------------------------------------------
// Feature flags
// ---------------------------------------------------------------------------

export const FeatureFlagsSchema = z.record(z.string(), z.boolean());
export type FeatureFlags = z.infer<typeof FeatureFlagsSchema>;

// ---------------------------------------------------------------------------
// Host type
// ---------------------------------------------------------------------------

export const HostTypeSchema = z.enum(["claude", "codex", "gemini", "kimi", "opencode"]);
export type HostType = z.infer<typeof HostTypeSchema>;

// ---------------------------------------------------------------------------
// MCP server config
// ---------------------------------------------------------------------------

export const McpServerConfigSchema = z.object({
  command: z.string(),
  args: z.array(z.string()),
  env: z.record(z.string(), z.string()).optional(),
});
export type McpServerConfig = z.infer<typeof McpServerConfigSchema>;

// ---------------------------------------------------------------------------
// Settings schema (settings.json shape)
// ---------------------------------------------------------------------------

export const SettingsSchema = z.object({
  permissions: z.object({
    allow: z.array(z.string()).optional(),
    deny: z.array(z.string()).optional(),
  }).optional(),
  hooks: z.record(z.string(), z.array(z.string())).optional(),
  _omg: z.object({
    features: FeatureFlagsSchema.optional(),
    preset: PresetNameSchema.optional(),
    mode: z.enum(["omg-only", "coexist"]).optional(),
  }).optional(),
}).passthrough();
export type Settings = z.infer<typeof SettingsSchema>;

// ---------------------------------------------------------------------------
// Preset config
// ---------------------------------------------------------------------------

export const PresetConfigSchema = z.object({
  name: PresetNameSchema,
  description: z.string(),
  features: FeatureFlagsSchema,
  hooks: z.array(z.string()),
});
export type PresetConfig = z.infer<typeof PresetConfigSchema>;

// ---------------------------------------------------------------------------
// Config transaction receipts (config_transaction.py)
// ---------------------------------------------------------------------------

export const PlannedWriteReceiptSchema = z.object({
  path: z.string(),
  content_hash: z.string(),
});
export type PlannedWriteReceipt = z.infer<typeof PlannedWriteReceiptSchema>;

export const ExecutedWriteReceiptSchema = z.object({
  path: z.string(),
  content_hash: z.string(),
  executed: z.boolean(),
  error: z.string().optional(),
});
export type ExecutedWriteReceipt = z.infer<typeof ExecutedWriteReceiptSchema>;

export const VerificationStatusSchema = z.enum(["ok", "mismatch", "missing"]);
export type VerificationStatus = z.infer<typeof VerificationStatusSchema>;

export const RollbackReceiptSchema = z.object({
  restored: z.array(z.string()),
  failed: z.array(z.string()),
});
export type RollbackReceipt = z.infer<typeof RollbackReceiptSchema>;

export const ConfigReceiptSchema = z.object({
  planned_writes: z.array(PlannedWriteReceiptSchema),
  executed_writes: z.array(ExecutedWriteReceiptSchema),
  backup_path: z.string(),
  verification: z.record(z.string(), VerificationStatusSchema),
  executed: z.boolean(),
  rollback: RollbackReceiptSchema.nullable(),
});
export type ConfigReceipt = z.infer<typeof ConfigReceiptSchema>;

// ---------------------------------------------------------------------------
// Doctor fix spec (compat.py → DoctorFixSpec) — runtime shape only
// ---------------------------------------------------------------------------

export const DoctorFixSpecSchema = z.object({
  fixable: z.boolean(),
  fixable_in_context: z.boolean(),
  suggestion: z.string(),
});
export type DoctorFixSpec = z.infer<typeof DoctorFixSpecSchema>;

// ---------------------------------------------------------------------------
// Canonical mode (adoption.py mode names)
// ---------------------------------------------------------------------------

export const CanonicalModeSchema = z.enum(["chill", "focused", "exploratory"]);
export type CanonicalMode = z.infer<typeof CanonicalModeSchema>;

// ---------------------------------------------------------------------------
// Runtime concurrency profile names
// ---------------------------------------------------------------------------

export const RuntimeConcurrencyProfileSchema = z.enum(["eco", "balanced", "turbo"]);
export type RuntimeConcurrencyProfile = z.infer<typeof RuntimeConcurrencyProfileSchema>;
