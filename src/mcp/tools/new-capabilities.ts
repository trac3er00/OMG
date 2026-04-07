import { z } from "zod";
import type { ToolRegistration } from "../../interfaces/mcp.js";

type EvidenceItem = {
  readonly type: string;
  readonly valid?: boolean | undefined;
  readonly path?: string | undefined;
};

function computeProofScore(evidence: readonly EvidenceItem[]): {
  score: number;
  band: "weak" | "developing" | "strong" | "complete";
  breakdown: {
    completeness: number;
    validity: number;
    diversity: number;
    traceability: number;
  };
} {
  if (evidence.length === 0) {
    return {
      score: 0,
      band: "weak",
      breakdown: {
        completeness: 0,
        validity: 0,
        diversity: 0,
        traceability: 0,
      },
    };
  }

  const total = evidence.length;
  const invalid = evidence.filter((item) => item.valid === false).length;
  const uniqueTypes = new Set(
    evidence
      .map((item) => item.type.trim())
      .filter((value) => value.length > 0),
  ).size;
  const pathBacked = evidence.filter((item) => item.path?.trim()).length;

  const breakdown = {
    completeness: Math.min(40, total * 20),
    validity: Math.max(0, 35 - invalid * 20),
    diversity: Math.min(15, uniqueTypes * 7.5),
    traceability: Math.min(10, pathBacked * 5),
  };
  const score = Math.max(
    0,
    Math.min(
      100,
      Math.trunc(
        breakdown.completeness +
          breakdown.validity +
          breakdown.diversity +
          breakdown.traceability,
      ),
    ),
  );

  return {
    score,
    band:
      score >= 85
        ? "complete"
        : score >= 65
          ? "strong"
          : score >= 40
            ? "developing"
            : "weak",
    breakdown,
  };
}

const proofScoreSchema = z.object({
  evidence: z.array(
    z.object({
      type: z.string(),
      valid: z.boolean().optional(),
      path: z.string().optional(),
    }),
  ),
});

const modelToggleSchema = z.object({
  mode: z.enum(["fast", "balanced", "quality"]),
});

const loopStatusSchema = z.object({
  history: z.array(z.any()).optional(),
});

const instantModeSchema = z.object({
  prompt: z.string(),
  target_dir: z.string().optional(),
});

export const newCapabilityTools: ToolRegistration[] = [
  {
    name: "omg_proof_score",
    description: "Compute ProofScore (0-100) for evidence list",
    inputSchema: {
      type: "object",
      properties: {
        evidence: {
          type: "array",
          items: {
            type: "object",
            properties: {
              type: { type: "string" },
              valid: { type: "boolean" },
              path: { type: "string" },
            },
            required: ["type"],
          },
        },
      },
      required: ["evidence"],
    },
    handler: async (args) => {
      const parsed = proofScoreSchema.parse(args);
      return computeProofScore(parsed.evidence);
    },
  },
  {
    name: "omg_model_toggle",
    description: "Set model routing mode (fast/balanced/quality)",
    inputSchema: {
      type: "object",
      properties: {
        mode: { type: "string", enum: ["fast", "balanced", "quality"] },
      },
      required: ["mode"],
    },
    handler: async (args) => {
      const parsed = modelToggleSchema.parse(args);
      return { mode: parsed.mode, set: true };
    },
  },
  {
    name: "omg_loop_status",
    description: "Query loop-breaker detection status",
    inputSchema: {
      type: "object",
      properties: {
        history: { type: "array" },
      },
    },
    handler: async (args) => {
      const parsed = loopStatusSchema.parse(args);
      return {
        detected: false,
        type: null,
        history_analyzed: parsed.history?.length ?? 0,
      };
    },
  },
  {
    name: "omg_instant_mode",
    description: "Trigger instant mode product generation",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string" },
        target_dir: { type: "string" },
      },
      required: ["prompt"],
    },
    handler: async (args) => {
      const parsed = instantModeSchema.parse(args);
      return {
        queued: true,
        prompt: parsed.prompt,
        ...(parsed.target_dir ? { target_dir: parsed.target_dir } : {}),
      };
    },
  },
];
