import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { join } from "node:path";
import { z } from "zod";

export const WORKSPACE_STATE_VERSION = "1.0.0";
export const DEFAULT_CONTEXT_DECAY_THRESHOLD = 0.3;
export const RECENT_REFERENCE_WINDOW_MINUTES = 10;

type TimestampLike = string | number | Date;

export interface WorkspaceReconstructionConfig {
  readonly freshnessThreshold: number;
  readonly retryLimit: number;
  readonly checkIntervalMinutes: number;
}

export interface FileReference {
  readonly path: string;
  readonly referencedAt: TimestampLike;
}

export interface ContextFreshnessInput {
  readonly fileReferences: readonly FileReference[];
  readonly sessionStartedAt: TimestampLike;
  readonly now?: TimestampLike;
}

export interface ContextDecayEvent {
  readonly detectedAt: string;
  readonly freshnessScore: number;
  readonly efficiencyRatio: number;
  readonly threshold: number;
  readonly recentFileReferences: number;
  readonly totalContextAgeMinutes: number;
}

export interface WorkspaceReconstructionRequest {
  readonly projectDir: string;
  readonly state: CompactCanonicalState;
  readonly fileReferences: readonly FileReference[];
  readonly sessionStartedAt: TimestampLike;
  readonly now?: TimestampLike;
  readonly contextDecayThreshold?: number;
  readonly config?: Partial<WorkspaceReconstructionConfig>;
}

export interface WorkspaceReconstructionResult {
  readonly state: CompactCanonicalState;
  readonly freshnessScore: number;
  readonly decayDetected: boolean;
  readonly attempts: number;
}

export const DEFAULT_WORKSPACE_RECONSTRUCTION_CONFIG: WorkspaceReconstructionConfig =
  {
    freshnessThreshold: 40,
    retryLimit: 2,
    checkIntervalMinutes: RECENT_REFERENCE_WINDOW_MINUTES,
  };

type ContextDecayListener = (event: ContextDecayEvent) => void;

const decayListeners = new Set<ContextDecayListener>();
const durabilityState: {
  contextFreshnessScore: number;
  decayEventCount: number;
  lastReconstructionAt?: string;
} = {
  contextFreshnessScore: 100,
  decayEventCount: 0,
};

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
  contextFreshnessScore: z.number().min(0).max(100).optional(),
  lastReconstructionAt: z.string().optional(),
  decayEventCount: z.number().int().min(0).optional(),
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
    contextFreshnessScore: opts.contextFreshnessScore,
    lastReconstructionAt: opts.lastReconstructionAt,
    decayEventCount: opts.decayEventCount,
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function toTimestamp(value: TimestampLike | undefined): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return value;
  if (typeof value === "string") return new Date(value).getTime();
  return Date.now();
}

function resolveFreshnessMetrics(input: ContextFreshnessInput): {
  recentFileReferences: number;
  totalContextAgeMinutes: number;
  efficiencyRatio: number;
} {
  const now = toTimestamp(input.now);
  const sessionStartedAt = toTimestamp(input.sessionStartedAt);
  const totalContextAgeMinutes = Math.max(1, (now - sessionStartedAt) / 60_000);
  const recentWindowMs = RECENT_REFERENCE_WINDOW_MINUTES * 60_000;
  const recentFileReferences = input.fileReferences.filter((reference) => {
    const ageMs = now - toTimestamp(reference.referencedAt);
    return ageMs >= 0 && ageMs <= recentWindowMs;
  }).length;

  return {
    recentFileReferences,
    totalContextAgeMinutes,
    efficiencyRatio: clamp(recentFileReferences / totalContextAgeMinutes, 0, 1),
  };
}

export function computeContextFreshnessScore(
  input: ContextFreshnessInput,
): number {
  const { efficiencyRatio } = resolveFreshnessMetrics(input);
  return clamp(Math.round(100 * efficiencyRatio), 0, 100);
}

export function onContextDecayDetected(
  listener: ContextDecayListener,
): () => void {
  decayListeners.add(listener);
  return () => decayListeners.delete(listener);
}

export function getWorkspaceDurabilityState(): Readonly<{
  contextFreshnessScore: number;
  decayEventCount: number;
  lastReconstructionAt?: string;
}> {
  return { ...durabilityState };
}

export function detectContextDecay(
  input: ContextFreshnessInput,
  contextDecayThreshold = DEFAULT_CONTEXT_DECAY_THRESHOLD,
): ContextDecayEvent & { readonly decayDetected: boolean } {
  const metrics = resolveFreshnessMetrics(input);
  const freshnessScore = computeContextFreshnessScore(input);
  durabilityState.contextFreshnessScore = freshnessScore;

  const event: ContextDecayEvent & { readonly decayDetected: boolean } = {
    detectedAt: new Date(toTimestamp(input.now)).toISOString(),
    freshnessScore,
    efficiencyRatio: metrics.efficiencyRatio,
    threshold: contextDecayThreshold,
    recentFileReferences: metrics.recentFileReferences,
    totalContextAgeMinutes: metrics.totalContextAgeMinutes,
    decayDetected: metrics.efficiencyRatio < contextDecayThreshold,
  };

  if (event.decayDetected) {
    durabilityState.decayEventCount += 1;
    for (const listener of decayListeners) {
      try {
        listener(event);
      } catch {
        void 0;
      }
    }
  }

  return event;
}

function mergeConfig(
  config?: Partial<WorkspaceReconstructionConfig>,
): WorkspaceReconstructionConfig {
  return {
    freshnessThreshold:
      config?.freshnessThreshold ??
      DEFAULT_WORKSPACE_RECONSTRUCTION_CONFIG.freshnessThreshold,
    retryLimit:
      config?.retryLimit ?? DEFAULT_WORKSPACE_RECONSTRUCTION_CONFIG.retryLimit,
    checkIntervalMinutes:
      config?.checkIntervalMinutes ??
      DEFAULT_WORKSPACE_RECONSTRUCTION_CONFIG.checkIntervalMinutes,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function reconstructWorkspace(
  request: WorkspaceReconstructionRequest,
): Promise<WorkspaceReconstructionResult> {
  const config = mergeConfig(request.config);
  const decay = detectContextDecay(
    request.now === undefined
      ? {
          fileReferences: request.fileReferences,
          sessionStartedAt: request.sessionStartedAt,
        }
      : {
          fileReferences: request.fileReferences,
          sessionStartedAt: request.sessionStartedAt,
          now: request.now,
        },
    request.contextDecayThreshold ?? DEFAULT_CONTEXT_DECAY_THRESHOLD,
  );
  const nowIso = new Date(toTimestamp(request.now)).toISOString();
  let lastError: unknown;

  for (let attempt = 0; attempt <= config.retryLimit; attempt++) {
    try {
      let existingState: CompactCanonicalState | null = null;
      try {
        existingState = await Promise.resolve(
          deserializeState(request.projectDir),
        );
      } catch (error) {
        throw new Error(
          `Failed to load workspace state for reconstruction: ${String(error)}`,
        );
      }

      let reconstructedState: CompactCanonicalState;
      try {
        const baseState = existingState ?? request.state;
        reconstructedState = createCompactState(baseState.goal, {
          context_version: Math.max(
            baseState.context_version,
            request.state.context_version,
          ),
          evidence_index: request.state.evidence_index,
          open_hypotheses: request.state.open_hypotheses,
          decision_log: request.state.decision_log,
          next_actions: request.state.next_actions,
          contextFreshnessScore: decay.freshnessScore,
          lastReconstructionAt: nowIso,
          decayEventCount: durabilityState.decayEventCount,
        });
      } catch (error) {
        throw new Error(
          `Failed to build reconstructed workspace state: ${String(error)}`,
        );
      }

      try {
        await Promise.resolve(
          serializeState(reconstructedState, request.projectDir),
        );
      } catch (error) {
        throw new Error(
          `Failed to persist reconstructed workspace state: ${String(error)}`,
        );
      }

      durabilityState.contextFreshnessScore = decay.freshnessScore;
      durabilityState.lastReconstructionAt = nowIso;

      return {
        state: reconstructedState,
        freshnessScore: decay.freshnessScore,
        decayDetected: decay.decayDetected,
        attempts: attempt + 1,
      };
    } catch (error) {
      lastError = error;
      if (attempt >= config.retryLimit) break;
      await sleep(100 * 2 ** attempt);
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Workspace reconstruction failed");
}
