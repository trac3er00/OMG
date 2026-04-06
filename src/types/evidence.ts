/**
 * Evidence and verification type definitions — full inventory.
 * Ported from Python TypedDict definitions in runtime/.
 */
import { z } from "zod";

// Re-export shared boundary types
export type {
  ClaimVerdict,
  EvidenceProfile,
  ProofScore,
  EvidenceType,
  Finding,
  ProofGateResult,
  ProofVerdict,
} from "../interfaces/evidence.js";

// ---------------------------------------------------------------------------
// Proof chain entry
// ---------------------------------------------------------------------------

export const ProofStepStatusSchema = z.enum([
  "pass",
  "fail",
  "skip",
  "pending",
]);
export type ProofStepStatus = z.infer<typeof ProofStepStatusSchema>;

export const ProofChainEntrySchema = z.object({
  step: z.string(),
  evidence_type: z.string(),
  artifact_path: z.string().optional(),
  status: ProofStepStatusSchema,
  timestamp: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
});
export type ProofChainEntry = z.infer<typeof ProofChainEntrySchema>;

// ---------------------------------------------------------------------------
// Artifact parse result
// ---------------------------------------------------------------------------

export const ArtifactParseResultSchema = z.object({
  artifact_type: z.string(),
  path: z.string(),
  parsed: z.boolean(),
  summary: z.record(z.string(), z.unknown()),
  raw: z.record(z.string(), z.unknown()).optional(),
  error: z.string().optional(),
});
export type ArtifactParseResult = z.infer<typeof ArtifactParseResultSchema>;

// ---------------------------------------------------------------------------
// Test intent lock (test_intent_lock)
// ---------------------------------------------------------------------------

export const TestIntentLockSchema = z.object({
  locked: z.boolean(),
  lock_id: z.string().optional(),
  locked_at: z.string().optional(),
  run_id: z.string().optional(),
  reason: z.string().optional(),
});
export type TestIntentLock = z.infer<typeof TestIntentLockSchema>;

// ---------------------------------------------------------------------------
// SARIF format
// ---------------------------------------------------------------------------

export const SarifToolDriverSchema = z.object({
  name: z.string(),
  version: z.string().optional(),
});

export const SarifRunSchema = z.object({
  tool: z.object({ driver: SarifToolDriverSchema }),
  results: z.array(z.record(z.string(), z.unknown())),
});

export const SarifSchema = z.object({
  version: z.string(),
  runs: z.array(SarifRunSchema),
});
export type Sarif = z.infer<typeof SarifSchema>;

// ---------------------------------------------------------------------------
// Evidence profile Zod schema (matches interfaces/evidence.ts)
// ---------------------------------------------------------------------------

export const EvidenceTypeSchema = z.enum([
  "junit",
  "coverage",
  "sarif",
  "browser_trace",
  "proof_chain",
  "test_intent_lock",
]);

export const EvidenceProfileSchema = z.object({
  required: z.array(EvidenceTypeSchema),
  optional: z.array(EvidenceTypeSchema),
  minCoverage: z.number().optional(),
  maxAge: z.number().optional(),
});

// ---------------------------------------------------------------------------
// Proof gate result Zod schema (matches interfaces/evidence.ts)
// ---------------------------------------------------------------------------

export const ProofVerdictSchema = z.enum([
  "pass",
  "fail",
  "blocked",
  "pending",
]);

export const ProofScoreSchema = z.object({
  score: z.number().min(0).max(100),
  band: z.enum(["weak", "developing", "strong", "complete"]),
  breakdown: z.record(z.string(), z.number().min(0).max(100)),
});

export const ProofGateResultSchema = z.object({
  status: ProofVerdictSchema,
  blockers: z.array(z.string()),
  requiredPrimitives: z.array(EvidenceTypeSchema),
  evidenceSummary: z.record(z.string(), z.unknown()),
  proofScore: ProofScoreSchema,
});

// ---------------------------------------------------------------------------
// Claim verdict Zod schema (matches interfaces/evidence.ts)
// ---------------------------------------------------------------------------

export const ClaimVerdictSchema = z.object({
  verdict: z.enum(["accept", "reject", "warn"]),
  reasons: z.array(z.string()),
  evidenceSummary: z.record(z.string(), z.unknown()),
  confidence: z.number().min(0).max(1),
  proofScore: ProofScoreSchema,
});
