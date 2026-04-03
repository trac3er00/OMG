import { z } from "zod";

export const REPRODUCIBILITY_RUNS = 10;

export const ReproducibilityResultSchema = z.object({
  layer: z.literal(4),
  target: z.string(),
  runs: z.number().int().min(0),
  unique_outputs: z.number().int().min(0),
  score: z.number().min(0).max(1),
  is_deterministic: z.boolean(),
  sample_outputs: z.array(z.string()).max(3),
  status: z.enum(["pass", "fail", "skip"]),
});
export type ReproducibilityResult = z.infer<typeof ReproducibilityResultSchema>;

export const BehavioralDiffResultSchema = z.object({
  layer: z.literal(5),
  target: z.string(),
  baseline_version: z.string(),
  current_version: z.string(),
  additions: z.array(z.string()),
  removals: z.array(z.string()),
  changes: z.array(
    z.object({ field: z.string(), from: z.string(), to: z.string() }),
  ),
  similarity_score: z.number().min(0).max(1),
  status: z.enum(["pass", "fail", "skip"]),
});
export type BehavioralDiffResult = z.infer<typeof BehavioralDiffResultSchema>;

const DETERMINISM_THRESHOLD = 0.8;

export function measureReproducibility(
  outputs: readonly string[],
): ReproducibilityResult {
  if (outputs.length === 0) {
    return ReproducibilityResultSchema.parse({
      layer: 4,
      target: "unknown",
      runs: 0,
      unique_outputs: 0,
      score: 0,
      is_deterministic: false,
      sample_outputs: [],
      status: "skip",
    });
  }

  const unique = new Set(outputs);
  const score = 1 - (unique.size - 1) / Math.max(outputs.length - 1, 1);
  const is_deterministic = score >= DETERMINISM_THRESHOLD;

  return ReproducibilityResultSchema.parse({
    layer: 4,
    target: "module",
    runs: outputs.length,
    unique_outputs: unique.size,
    score,
    is_deterministic,
    sample_outputs: [...outputs].slice(0, 3),
    status: is_deterministic ? "pass" : "fail",
  });
}

export function computeBehavioralDiff(
  baseline: Record<string, string>,
  current: Record<string, string>,
  target: string,
  baselineVersion = "prev",
  currentVersion = "current",
): BehavioralDiffResult {
  const baselineKeys = new Set(Object.keys(baseline));
  const currentKeys = new Set(Object.keys(current));

  const additions = [...currentKeys].filter((k) => !baselineKeys.has(k));
  const removals = [...baselineKeys].filter((k) => !currentKeys.has(k));
  const sharedKeys = [...baselineKeys].filter((k) => currentKeys.has(k));
  const changes = sharedKeys
    .filter((k) => baseline[k] !== current[k])
    .map((k) => ({ field: k, from: baseline[k] ?? "", to: current[k] ?? "" }));

  const totalFields = Math.max(baselineKeys.size, currentKeys.size);
  const changedCount = additions.length + removals.length + changes.length;
  const similarity_score =
    totalFields === 0 ? 1.0 : 1 - changedCount / totalFields;

  return BehavioralDiffResultSchema.parse({
    layer: 5,
    target,
    baseline_version: baselineVersion,
    current_version: currentVersion,
    additions,
    removals,
    changes,
    similarity_score: Math.max(0, similarity_score),
    status: similarity_score >= 0.8 ? "pass" : "fail",
  });
}
