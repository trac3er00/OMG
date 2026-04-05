/**
 * Security type definitions — full inventory.
 * Ported from Python TypedDict definitions in runtime/ and hooks/.
 */
import { z } from "zod";

// Re-export shared boundary types
export type {
  CredentialEntry,
  InjectionDetectionResult,
  MutationCheck,
  SecretGuardResult,
  TrustManifest,
} from "../interfaces/security.js";

export type {
  MutationOperation,
  PolicyAction,
  PolicyDecision,
  RiskLevel,
} from "../interfaces/policy.js";

export type {
  DefenseState,
  TrustTier,
  TrustState,
} from "../interfaces/state.js";

// ---------------------------------------------------------------------------
// Defense state Zod schema (matches interfaces/state.ts DefenseState)
// ---------------------------------------------------------------------------

export const RiskLevelSchema = z.enum(["low", "medium", "high", "critical"]);

export const DefenseStateSchema = z.object({
  riskLevel: RiskLevelSchema,
  injectionHits: z.number().int().min(0),
  contaminationScore: z.number().min(0).max(1),
  overthinkingScore: z.number().min(0).max(1),
  prematureFixerScore: z.number().min(0).max(1),
  actions: z.array(z.string()),
  reasons: z.array(z.string()),
  updatedAt: z.string(),
});

// ---------------------------------------------------------------------------
// Policy decision Zod schema (matches interfaces/policy.ts PolicyDecision)
// ---------------------------------------------------------------------------

export const PolicyActionSchema = z.enum(["allow", "warn", "deny", "block", "ask"]);

export const PolicyDecisionSchema = z.object({
  action: PolicyActionSchema,
  reason: z.string(),
  riskLevel: RiskLevelSchema,
  tags: z.array(z.string()),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

// ---------------------------------------------------------------------------
// Mutation check Zod schema (matches interfaces/security.ts MutationCheck)
// ---------------------------------------------------------------------------

export const MutationOperationSchema = z.enum(["write", "edit", "multiedit", "bash_mutation"]);

export const MutationCheckSchema = z.object({
  allowed: z.boolean(),
  reason: z.string(),
  operation: MutationOperationSchema,
  decision: PolicyDecisionSchema,
  exemption: z.string().optional(),
  riskScore: z.number().min(0).max(100),
});

// ---------------------------------------------------------------------------
// Trust tier Zod schema (matches interfaces/state.ts TrustTier)
// ---------------------------------------------------------------------------

export const TrustTierSchema = z.enum(["local", "balanced", "research", "browser"]);

export const TrustStateSchema = z.object({
  active: z.boolean(),
  lastSourceType: z.string(),
  lastTrustTier: TrustTierSchema,
  trustScore: z.number().min(0).max(1),
});

// ---------------------------------------------------------------------------
// Firewall rule (firewall.py)
// ---------------------------------------------------------------------------

export const FirewallSeveritySchema = z.enum(["critical", "high", "medium", "low"]);
export type FirewallSeverity = z.infer<typeof FirewallSeveritySchema>;

export const FirewallRuleSchema = z.object({
  /** Regex pattern as a string */
  pattern: z.string(),
  label: z.string(),
  severity: FirewallSeveritySchema,
  action: z.enum(["deny", "warn", "ask"]),
});
export type FirewallRule = z.infer<typeof FirewallRuleSchema>;

// ---------------------------------------------------------------------------
// Finding (matches interfaces/evidence.ts Finding, Zod schema)
// ---------------------------------------------------------------------------

export const FindingSeveritySchema = z.enum(["critical", "high", "medium", "low", "info"]);

export const FindingSchema = z.object({
  id: z.string(),
  severity: FindingSeveritySchema,
  message: z.string(),
  path: z.string(),
  line: z.number().int().optional(),
  waived: z.boolean(),
  waiverReason: z.string().optional(),
});
export type FindingRecord = z.infer<typeof FindingSchema>;

// ---------------------------------------------------------------------------
// Policy pack (policy_pack_loader.py → PolicyPack)
// ---------------------------------------------------------------------------

export const NetworkPostureSchema = z.enum(["open", "restricted", "airgapped"]);
export type NetworkPosture = z.infer<typeof NetworkPostureSchema>;

export const DataSharingSchema = z.enum(["allowed", "restricted", "prohibited"]);
export type DataSharing = z.infer<typeof DataSharingSchema>;

export const PolicyPackSchema = z.object({
  id: z.string(),
  description: z.string(),
  tool_restrictions: z.array(z.string()),
  network_posture: NetworkPostureSchema,
  approval_threshold: z.number().int(),
  protected_paths: z.array(z.string()),
  evidence_requirements: z.array(z.string()),
  data_sharing: DataSharingSchema,
});
export type PolicyPack = z.infer<typeof PolicyPackSchema>;

// ---------------------------------------------------------------------------
// Injection detection Zod schema
// ---------------------------------------------------------------------------

export const InjectionDetectionResultSchema = z.object({
  detected: z.boolean(),
  confidence: z.number().min(0).max(1),
  patterns: z.array(z.string()),
  sanitizedContent: z.string(),
  quarantined: z.array(z.string()),
});

// ---------------------------------------------------------------------------
// Credential entry Zod schema
// ---------------------------------------------------------------------------

export const CredentialEntrySchema = z.object({
  provider: z.string(),
  key: z.string(),
  encryptedValue: z.string(),
  createdAt: z.string(),
  expiresAt: z.string().optional(),
  usageCount: z.number().int(),
  lastUsed: z.string().optional(),
});
