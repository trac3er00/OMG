import { z } from "zod";

export const EVIDENCE_SCHEMA_VERSION = "1.0.0";
export const LEGACY_SCHEMA_VERSION = "0.9.0";

const semverRegex = /^\d+\.\d+\.\d+$/;

// Base schema every evidence artifact must satisfy
export const EvidenceBaseSchema = z.object({
  schema_version: z.string().regex(semverRegex).default(LEGACY_SCHEMA_VERSION),
  artifact_type: z.string(),
});

export type EvidenceBase = z.infer<typeof EvidenceBaseSchema>;

// Migrate old artifacts (no version field) to LEGACY_SCHEMA_VERSION
export function migrateArtifact(
  artifact: unknown,
): EvidenceBase & Record<string, unknown> {
  if (typeof artifact !== "object" || artifact === null) {
    throw new Error("Cannot migrate non-object artifact");
  }
  const obj = artifact as Record<string, unknown>;
  return {
    ...obj,
    schema_version:
      typeof obj["schema_version"] === "string"
        ? obj["schema_version"]
        : LEGACY_SCHEMA_VERSION,
    artifact_type:
      typeof obj["artifact_type"] === "string"
        ? obj["artifact_type"]
        : "unknown",
  };
}

// Validate any artifact against base schema
export function validateEvidenceArtifact(artifact: unknown): {
  valid: boolean;
  error?: string;
} {
  const result = EvidenceBaseSchema.safeParse(artifact);
  if (result.success) return { valid: true };
  return { valid: false, error: result.error.message };
}

// Specific schemas for known artifact types
export const JUnitArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("junit"),
  parsed: z.boolean(),
  summary: z
    .object({
      tests: z.number(),
      failures: z.number(),
      errors: z.number(),
      time: z.number(),
      failureMessages: z.array(z.string()),
    })
    .or(z.record(z.string(), z.unknown())),
});

export const CoverageArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("coverage"),
  line_rate: z.number().min(0).max(1),
  branch_rate: z.number().min(0).max(1).optional(),
});

export const SarifArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("sarif"),
  runs: z.array(z.unknown()),
});

export const ClaimJudgeArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("claim_judge"),
  verdict: z.enum(["accept", "reject", "warn"]),
  confidence: z.number().min(0).max(1),
  reasons: z.array(z.string()),
});

export const ProofGateArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("proof_gate"),
  status: z.enum(["pass", "fail", "blocked", "pending"]),
  blockers: z.array(z.string()),
});

export const TestIntentLockArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("test_intent_lock"),
  lock_id: z.string(),
  status: z.enum(["locked", "verified", "released", "fail"]),
});

export const SecurityCheckArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("security_check"),
  findings: z.array(
    z.object({
      severity: z.enum(["critical", "high", "medium", "low", "info"]),
      message: z.string(),
    }),
  ),
});

export const EvalGateArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("eval_gate"),
  verdict: z.enum(["pass", "fail", "warn"]),
  baseline_comparison: z.record(z.string(), z.unknown()).optional(),
});

export const DataLineageArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("data_lineage"),
  source: z.string(),
  transformations: z.array(z.string()),
});

export const IncidentReplayArtifactSchema = EvidenceBaseSchema.extend({
  artifact_type: z.literal("incident_replay"),
  incident_id: z.string(),
  reproduction_steps: z.array(z.string()),
});

// Registry of all known schemas
export const ARTIFACT_SCHEMAS: Record<string, z.ZodSchema> = {
  junit: JUnitArtifactSchema,
  coverage: CoverageArtifactSchema,
  sarif: SarifArtifactSchema,
  claim_judge: ClaimJudgeArtifactSchema,
  proof_gate: ProofGateArtifactSchema,
  test_intent_lock: TestIntentLockArtifactSchema,
  security_check: SecurityCheckArtifactSchema,
  eval_gate: EvalGateArtifactSchema,
  data_lineage: DataLineageArtifactSchema,
  incident_replay: IncidentReplayArtifactSchema,
};

export function validateArtifactByType(artifact: unknown): {
  valid: boolean;
  error?: string;
} {
  const migrated = migrateArtifact(artifact);
  const schema = ARTIFACT_SCHEMAS[migrated.artifact_type];
  if (schema == null) {
    // Unknown types pass base validation only
    return validateEvidenceArtifact(migrated);
  }
  const result = schema.safeParse(migrated);
  if (result.success) return { valid: true };
  return { valid: false, error: result.error.message };
}
