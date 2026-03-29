/**
 * Context engine type definitions.
 * Ported from Python shapes in runtime/context_engine.py and related modules.
 */
import { z } from "zod";

// Re-export shared boundary types
export type {
  ContextPacket,
  ProfileDigest,
  StateResolver,
} from "../interfaces/state.js";

// ---------------------------------------------------------------------------
// Context packet Zod schema (matches interfaces/state.ts ContextPacket)
// ---------------------------------------------------------------------------

export const ContextPacketSchema = z.object({
  packetVersion: z.string(),
  summary: z.string(),
  artifactPointers: z.array(z.string()),
  provenancePointers: z.array(z.string()),
  governance: z.record(z.string(), z.unknown()),
  runId: z.string(),
  deltaOnly: z.boolean(),
});

// ---------------------------------------------------------------------------
// Profile digest Zod schema (matches interfaces/state.ts ProfileDigest)
// ---------------------------------------------------------------------------

export const ProfileDigestSchema = z.object({
  architectureRequests: z.array(z.string()),
  constraints: z.array(z.string()),
  tags: z.array(z.string()),
  summary: z.string(),
  confidence: z.number().min(0).max(1),
});

// ---------------------------------------------------------------------------
// Handoff snapshot
// ---------------------------------------------------------------------------

export const HandoffSnapshotSchema = z.object({
  snapshot_id: z.string(),
  task_focus: z.string(),
  context_summary: z.string(),
  created_at: z.string(),
  run_id: z.string(),
  artifact_paths: z.array(z.string()),
});
export type HandoffSnapshot = z.infer<typeof HandoffSnapshotSchema>;

// ---------------------------------------------------------------------------
// Clarification state
// ---------------------------------------------------------------------------

export const ClarificationStateSchema = z.object({
  required: z.boolean(),
  question: z.string().optional(),
  options: z.array(z.string()).optional(),
  ambiguity_score: z.number().min(0).max(1),
});
export type ClarificationState = z.infer<typeof ClarificationStateSchema>;

// ---------------------------------------------------------------------------
// Context pressure
// ---------------------------------------------------------------------------

export const ContextPressureLevelSchema = z.enum(["low", "medium", "high", "critical"]);
export type ContextPressureLevel = z.infer<typeof ContextPressureLevelSchema>;

export const ContextPressureSchema = z.object({
  tool_count: z.number().int(),
  threshold: z.number().int(),
  ratio: z.number().min(0),
  pressure_level: ContextPressureLevelSchema,
  recommendation: z.string(),
});
export type ContextPressure = z.infer<typeof ContextPressureSchema>;
