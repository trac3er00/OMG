import { z } from "zod";
import type { OrchestrationMode, OrchestrationTask } from "./session.js";

export const ModeConfigSchema = z.object({
  mode: z.enum(["ultrawork", "team", "sequential"]),
  concurrency: z.number().int().positive(),
  taskReordering: z.boolean(),
  leaderTaskId: z.string().optional(),
  failFast: z.boolean(),
  budgetMultiplier: z.number().positive(),
});
export type ModeConfig = z.infer<typeof ModeConfigSchema>;

const MODE_DEFAULTS: Record<OrchestrationMode, ModeConfig> = {
  ultrawork: {
    mode: "ultrawork",
    concurrency: 8,
    taskReordering: true,
    failFast: false,
    budgetMultiplier: 1.0,
  },
  team: {
    mode: "team",
    concurrency: 4,
    taskReordering: false,
    failFast: false,
    budgetMultiplier: 1.5,
  },
  sequential: {
    mode: "sequential",
    concurrency: 1,
    taskReordering: false,
    failFast: true,
    budgetMultiplier: 0.5,
  },
};

export function getModeConfig(
  mode: OrchestrationMode,
  overrides: Partial<ModeConfig> = {},
): ModeConfig {
  const defaults = MODE_DEFAULTS[mode];
  return ModeConfigSchema.parse({ ...defaults, ...overrides, mode });
}

export interface TaskPlan {
  readonly tasks: readonly OrchestrationTask[];
  readonly waves: readonly ReadonlyArray<string>[];
  readonly leaderTaskId: string | null;
}

export function planTasks(
  tasks: readonly OrchestrationTask[],
  config: ModeConfig,
): TaskPlan {
  if (tasks.length === 0) {
    return { tasks: [], waves: [], leaderTaskId: null };
  }

  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const inDegree = new Map<string, number>();
  const dependents = new Map<string, string[]>();

  for (const t of tasks) {
    inDegree.set(t.id, 0);
    dependents.set(t.id, []);
  }

  for (const t of tasks) {
    for (const dep of t.deps) {
      if (taskMap.has(dep)) {
        inDegree.set(t.id, (inDegree.get(t.id) ?? 0) + 1);
        dependents.get(dep)?.push(t.id);
      }
    }
  }

  const waves: string[][] = [];
  const remaining = new Set(tasks.map((t) => t.id));

  while (remaining.size > 0) {
    const ready = [...remaining].filter((id) => (inDegree.get(id) ?? 0) === 0);
    if (ready.length === 0) {
      throw new Error("Cycle detected in task dependencies");
    }

    if (config.taskReordering) {
      ready.sort((a, b) => {
        const pa = priorityValue(taskMap.get(a)?.priority ?? "medium");
        const pb = priorityValue(taskMap.get(b)?.priority ?? "medium");
        return pa - pb;
      });
    }

    const wave =
      config.mode === "sequential"
        ? [ready[0]]
        : ready.slice(0, config.concurrency);

    waves.push(wave);

    for (const id of wave) {
      remaining.delete(id);
      for (const dep of dependents.get(id) ?? []) {
        inDegree.set(dep, (inDegree.get(dep) ?? 0) - 1);
      }
    }
  }

  let leaderTaskId: string | null = null;
  if (config.mode === "team" && config.leaderTaskId != null) {
    leaderTaskId = taskMap.has(config.leaderTaskId)
      ? config.leaderTaskId
      : null;
  }

  return {
    tasks: config.taskReordering ? reorderByWaves(tasks, waves) : tasks,
    waves,
    leaderTaskId,
  };
}

export function estimateDuration(plan: TaskPlan, config: ModeConfig): number {
  let totalMs = 0;
  for (const wave of plan.waves) {
    const waveTasks = wave.map((id) => plan.tasks.find((t) => t.id === id));
    if (config.mode === "sequential") {
      for (const t of waveTasks) {
        totalMs += t?.timeout_ms ?? 120_000;
      }
    } else {
      const maxInWave = Math.max(
        ...waveTasks.map((t) => t?.timeout_ms ?? 120_000),
      );
      totalMs += maxInWave;
    }
  }
  return totalMs;
}

function priorityValue(priority: string): number {
  if (priority === "high") return 0;
  if (priority === "low") return 2;
  return 1;
}

function reorderByWaves(
  tasks: readonly OrchestrationTask[],
  waves: readonly ReadonlyArray<string>[],
): OrchestrationTask[] {
  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const ordered: OrchestrationTask[] = [];
  for (const wave of waves) {
    for (const id of wave) {
      const task = taskMap.get(id);
      if (task) ordered.push(task);
    }
  }
  return ordered;
}
