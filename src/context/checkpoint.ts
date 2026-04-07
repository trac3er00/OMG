import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { join } from "node:path";
import { readdirSync, mkdirSync, existsSync, renameSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { z } from "zod";
import {
  type CompactCanonicalState,
  serializeState,
  deserializeState,
  getWorkspaceDurabilityState,
} from "./workspace-reconstruction.js";

export const CHECKPOINT_VERSION = "1.0.0";
export const DEFAULT_CHECKPOINT_INTERVAL = 50;
export const MAX_ACTIVE_CHECKPOINTS = 5;

const CheckpointMetaSchema = z.object({
  checkpoint_id: z.string(),
  created_at: z.string(),
  tool_call_count: z.number().int(),
  context_version: z.number().int(),
  goal_summary: z.string(),
  contextFreshnessScore: z.number().min(0).max(100).optional(),
  lastReconstructionAt: z.string().optional(),
  decayEventCount: z.number().int().min(0).optional(),
});
type CheckpointMeta = z.infer<typeof CheckpointMetaSchema>;

export interface CheckpointResult {
  readonly checkpoint_id: string;
  readonly path: string;
  readonly tool_call_count: number;
}

export interface RestorationResult {
  readonly state: CompactCanonicalState;
  readonly checkpoint_id: string;
  readonly elapsed_ms: number;
}

export class CheckpointSystem {
  private toolCallCount = 0;
  private readonly checkpointDir: string;
  private readonly archiveDir: string;
  private readonly interval: number;

  constructor(
    private readonly projectDir: string,
    interval = DEFAULT_CHECKPOINT_INTERVAL,
  ) {
    this.interval = interval;
    this.checkpointDir = join(projectDir, ".omg", "state", "checkpoints");
    this.archiveDir = join(
      projectDir,
      ".omg",
      "state",
      "checkpoints",
      "archive",
    );
  }

  onToolCall(): CheckpointResult | null {
    this.toolCallCount++;
    if (this.toolCallCount % this.interval === 0) {
      return this.saveCheckpoint();
    }
    return null;
  }

  saveCheckpoint(): CheckpointResult {
    const state = deserializeState(this.projectDir);
    const durabilityState = getWorkspaceDurabilityState();
    if (state == null) {
      const empty: CompactCanonicalState = {
        schema_version: "1.0.0",
        context_version: 0,
        goal: "",
        evidence_index: [],
        open_hypotheses: [],
        decision_log: [],
        next_actions: [],
        reconstructed_at: new Date().toISOString(),
      };
      serializeState(empty, this.projectDir);
    }

    const checkpointId = randomBytes(8).toString("hex");
    mkdirSync(this.checkpointDir, { recursive: true });

    const meta: CheckpointMeta = CheckpointMetaSchema.parse({
      checkpoint_id: checkpointId,
      created_at: new Date().toISOString(),
      tool_call_count: this.toolCallCount,
      context_version: state?.context_version ?? 0,
      goal_summary: (state?.goal ?? "").slice(0, 80),
      contextFreshnessScore:
        state?.contextFreshnessScore ?? durabilityState.contextFreshnessScore,
      lastReconstructionAt:
        state?.lastReconstructionAt ?? durabilityState.lastReconstructionAt,
      decayEventCount:
        state?.decayEventCount ?? durabilityState.decayEventCount,
    });

    const checkpointPath = join(this.checkpointDir, `${checkpointId}.json`);
    const currentState = deserializeState(this.projectDir);
    atomicWriteJson(checkpointPath, { meta, state: currentState });
    this.gc();

    return {
      checkpoint_id: checkpointId,
      path: checkpointPath,
      tool_call_count: this.toolCallCount,
    };
  }

  restoreLatest(projectDir?: string): RestorationResult | null {
    const target = projectDir ?? this.projectDir;
    const start = Date.now();

    if (!existsSync(this.checkpointDir)) return null;

    const files = readdirSync(this.checkpointDir)
      .filter((f) => f.endsWith(".json") && !f.includes("archive"))
      .map((f) => {
        const raw = readJsonFile<{
          meta: CheckpointMeta;
          state: CompactCanonicalState;
        }>(join(this.checkpointDir, f));
        return raw ? { file: f, data: raw } : null;
      })
      .filter(Boolean)
      .sort(
        (a, b) =>
          (b!.data.meta.tool_call_count ?? 0) -
          (a!.data.meta.tool_call_count ?? 0),
      );

    const latest = files[0];
    if (!latest) return null;

    const { state, meta } = latest.data;
    serializeState(state, target);

    return {
      state,
      checkpoint_id: meta.checkpoint_id,
      elapsed_ms: Date.now() - start,
    };
  }

  getToolCallCount(): number {
    return this.toolCallCount;
  }

  private gc(): void {
    if (!existsSync(this.checkpointDir)) return;
    const files = readdirSync(this.checkpointDir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => ({
        file: f,
        path: join(this.checkpointDir, f),
        mtime: 0,
      }));

    if (files.length > MAX_ACTIVE_CHECKPOINTS) {
      mkdirSync(this.archiveDir, { recursive: true });
      const toArchive = files.slice(0, files.length - MAX_ACTIVE_CHECKPOINTS);
      for (const f of toArchive) {
        const archivePath = join(this.archiveDir, f.file);
        try {
          renameSync(f.path, archivePath);
        } catch {
          void 0;
        }
      }
    }
  }
}
