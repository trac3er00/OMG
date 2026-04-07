export interface Task {
  id: string;
  description: string;
  dependsOn: string[];
}

export interface Wave {
  waveNumber: number;
  tasks: Task[];
  canRunInParallel: boolean;
}

export interface WaveOptimizationResult {
  waves: Wave[];
  totalTasks: number;
  maxParallelism: number;
  criticalPathLength: number;
}

/**
 * Kahn's algorithm: group tasks into parallel waves by topological level.
 * @throws Error on dependency cycles or unknown dependency references
 */
export function optimizeWaves(tasks: Task[]): WaveOptimizationResult {
  if (tasks.length === 0) {
    return {
      waves: [],
      totalTasks: 0,
      maxParallelism: 0,
      criticalPathLength: 0,
    };
  }

  const taskMap = new Map<string, Task>();
  for (const task of tasks) {
    taskMap.set(task.id, task);
  }

  for (const task of tasks) {
    for (const dep of task.dependsOn) {
      if (!taskMap.has(dep)) {
        throw new Error(`Task "${task.id}" depends on unknown task "${dep}"`);
      }
    }
  }

  const waves: Wave[] = [];
  const resolved = new Set<string>();
  const remaining = new Set(tasks.map((t) => t.id));

  // Kahn's: each iteration collects all tasks whose deps are fully resolved → one wave
  while (remaining.size > 0) {
    const ready: Task[] = [];
    for (const id of remaining) {
      const task = taskMap.get(id)!;
      if (task.dependsOn.every((dep) => resolved.has(dep))) {
        ready.push(task);
      }
    }

    if (ready.length === 0) {
      const cycleIds = [...remaining].join(", ");
      throw new Error(`Dependency cycle detected among tasks: ${cycleIds}`);
    }

    ready.sort((a, b) => a.id.localeCompare(b.id));

    waves.push({
      waveNumber: waves.length + 1,
      tasks: ready,
      canRunInParallel: ready.length > 1,
    });

    for (const task of ready) {
      resolved.add(task.id);
      remaining.delete(task.id);
    }
  }

  return {
    waves,
    totalTasks: tasks.length,
    maxParallelism: Math.max(...waves.map((w) => w.tasks.length)),
    criticalPathLength: waves.length,
  };
}

/**
 * Validate wave plan: deps in earlier waves, no duplicates, correct count.
 */
export function validateWavePlan(result: WaveOptimizationResult): string[] {
  const violations: string[] = [];
  const taskWave = new Map<string, number>();
  const seenIds = new Set<string>();

  for (const wave of result.waves) {
    for (const task of wave.tasks) {
      if (seenIds.has(task.id)) {
        violations.push(`Task "${task.id}" appears in multiple waves`);
      }
      seenIds.add(task.id);
      taskWave.set(task.id, wave.waveNumber);
    }
  }

  for (const wave of result.waves) {
    for (const task of wave.tasks) {
      for (const dep of task.dependsOn) {
        const depWave = taskWave.get(dep);
        if (depWave === undefined) {
          violations.push(
            `Task "${task.id}" depends on "${dep}" which is not in the wave plan`,
          );
        } else if (depWave >= wave.waveNumber) {
          violations.push(
            `Task "${task.id}" (wave ${wave.waveNumber}) depends on "${dep}" (wave ${depWave}) which is not in an earlier wave`,
          );
        }
      }
    }
  }

  if (seenIds.size !== result.totalTasks) {
    violations.push(
      `Wave plan contains ${seenIds.size} tasks but totalTasks reports ${result.totalTasks}`,
    );
  }

  return violations;
}
