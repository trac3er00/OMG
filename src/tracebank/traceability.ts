export interface TraceLink {
  taskId: string;
  commitHash: string;
  commitMessage: string;
  timestamp: string;
  files: string[];
}

export interface TraceabilityReport {
  planId: string;
  generatedAt: string;
  links: TraceLink[];
  tasksWithCommits: string[];
  tasksWithoutCommits: string[];
}

/**
 * Known task-reference patterns in commit messages:
 *   [T14]  [task-14]  task-14  feat(T14):  T14
 */
const TASK_REF_PATTERNS: RegExp[] = [
  /\[T(\d+)\]/i, // [T14]
  /\[task[- ]?(\d+)\]/i, // [task-14], [task 14]
  /\btask[- ]?(\d+)\b/i, // task-14, task14
  /\bfeat\(T(\d+)\)/i, // feat(T14):
  /\bfix\(T(\d+)\)/i, // fix(T14):
  /\bchore\(T(\d+)\)/i, // chore(T14):
  /\brefactor\(T(\d+)\)/i, // refactor(T14):
  /\bT(\d+)\b/, // T14 (case-sensitive — avoids "the", "to", etc.)
];

/**
 * Extract task reference from commit message.
 * Looks for patterns like: [T14], task-14, feat(T14):, T14, etc.
 * Returns the canonical form "T{number}" or null.
 */
export function extractTaskReference(commitMessage: string): string | null {
  for (const pattern of TASK_REF_PATTERNS) {
    const match = pattern.exec(commitMessage);
    if (match?.[1]) {
      return `T${match[1]}`;
    }
  }
  return null;
}

/**
 * Create a trace link between a task and a commit.
 */
export function createTraceLink(
  taskId: string,
  commitHash: string,
  commitMessage: string,
  files: string[] = [],
): TraceLink {
  return {
    taskId,
    commitHash,
    commitMessage,
    timestamp: new Date().toISOString(),
    files,
  };
}

/**
 * Generate a traceability report for a plan.
 *
 * Partitions allTaskIds into those that have at least one link
 * and those that have none.
 */
export function generateTraceabilityReport(
  planId: string,
  links: TraceLink[],
  allTaskIds: string[],
): TraceabilityReport {
  const linked = new Set(links.map((l) => l.taskId));
  return {
    planId,
    generatedAt: new Date().toISOString(),
    links,
    tasksWithCommits: allTaskIds.filter((id) => linked.has(id)),
    tasksWithoutCommits: allTaskIds.filter((id) => !linked.has(id)),
  };
}

/**
 * Format commit message with task reference.
 *
 * If the message already contains the task ref, return it unchanged.
 * Otherwise append " [T{id}]".
 *
 * @example formatWithTaskRef("feat: add feature", "T14") → "feat: add feature [T14]"
 */
export function formatWithTaskRef(message: string, taskId: string): string {
  const canonical = taskId.startsWith("T") ? taskId : `T${taskId}`;

  if (message.includes(`[${canonical}]`)) {
    return message;
  }

  return `${message} [${canonical}]`;
}
