import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { join } from "node:path";
import { z } from "zod";

export const WORKSPACE_STATE_VERSION = "1.0.0";

export const CompactCanonicalStateSchema = z.object({
  schema_version: z.literal(WORKSPACE_STATE_VERSION),
  context_version: z.number().int().min(0),
  goal: z.string(),
  evidence_index: z.array(z.string()),
  open_hypotheses: z.array(z.string()),
  decision_log: z.array(
    z.object({
      decision: z.string(),
      rationale: z.string(),
      timestamp: z.string(),
    }),
  ),
  next_actions: z.array(z.string()),
  reconstructed_at: z.string(),
});

export type CompactCanonicalState = z.infer<typeof CompactCanonicalStateSchema>;

export interface ReconstructionQuality {
  readonly retention_rate: number;
  readonly fields_preserved: readonly string[];
  readonly fields_lost: readonly string[];
}

const STATE_FILE = "workspace-state.json";

export function createCompactState(
  goal: string,
  opts: Partial<
    Omit<
      CompactCanonicalState,
      "schema_version" | "context_version" | "goal" | "reconstructed_at"
    >
  > & {
    context_version?: number;
  } = {},
): CompactCanonicalState {
  return CompactCanonicalStateSchema.parse({
    schema_version: WORKSPACE_STATE_VERSION,
    context_version: opts.context_version ?? 0,
    goal,
    evidence_index: opts.evidence_index ?? [],
    open_hypotheses: opts.open_hypotheses ?? [],
    decision_log: opts.decision_log ?? [],
    next_actions: opts.next_actions ?? [],
    reconstructed_at: new Date().toISOString(),
  });
}

export function serializeState(
  state: CompactCanonicalState,
  projectDir: string,
): void {
  const stateDir = join(projectDir, ".omg", "state");
  const statePath = join(stateDir, STATE_FILE);
  atomicWriteJson(statePath, state);
}

export function deserializeState(
  projectDir: string,
): CompactCanonicalState | null {
  const statePath = join(projectDir, ".omg", "state", STATE_FILE);
  const raw = readJsonFile<unknown>(statePath);
  if (raw == null) return null;
  const result = CompactCanonicalStateSchema.safeParse(raw);
  if (!result.success) return null;
  return result.data;
}

export function measureRetentionQuality(
  original: CompactCanonicalState,
  reconstructed: CompactCanonicalState,
): ReconstructionQuality {
  const preserved: string[] = [];
  const lost: string[] = [];

  if (original.goal === reconstructed.goal) {
    preserved.push("goal");
  } else {
    lost.push("goal");
  }

  if (
    JSON.stringify(original.evidence_index) ===
    JSON.stringify(reconstructed.evidence_index)
  ) {
    preserved.push("evidence_index");
  } else if (reconstructed.evidence_index.length > 0) {
    preserved.push("evidence_index_partial");
  } else {
    lost.push("evidence_index");
  }

  if (
    JSON.stringify(original.decision_log) ===
    JSON.stringify(reconstructed.decision_log)
  ) {
    preserved.push("decision_log");
  } else if (reconstructed.decision_log.length > 0) {
    preserved.push("decision_log_partial");
  } else {
    lost.push("decision_log");
  }

  if (
    JSON.stringify(original.next_actions) ===
    JSON.stringify(reconstructed.next_actions)
  ) {
    preserved.push("next_actions");
  } else if (reconstructed.next_actions.length > 0) {
    preserved.push("next_actions_partial");
  } else {
    lost.push("next_actions");
  }

  if (
    JSON.stringify(original.open_hypotheses) ===
    JSON.stringify(reconstructed.open_hypotheses)
  ) {
    preserved.push("open_hypotheses");
  } else {
    lost.push("open_hypotheses");
  }

  const preservation_score =
    preserved.length / (preserved.length + lost.length);
  const goal_weight = original.goal === reconstructed.goal ? 0.4 : 0;
  const retention_rate = Math.min(1, goal_weight + preservation_score * 0.6);

  return {
    retention_rate,
    fields_preserved: preserved,
    fields_lost: lost,
  };
}
