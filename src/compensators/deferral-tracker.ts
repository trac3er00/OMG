export interface DeferralResult {
  detected: boolean;
  matchedPhrases: string[];
  warningMessage?: string;
}

const DEFERRAL_PATTERNS = [
  /in a follow-?up session/i,
  /in a future session/i,
  /next session/i,
  /later session/i,
  /I['']ll handle this later/i,
  /will be addressed later/i,
  /out of scope for now/i,
  /deferred to/i,
  /left as an exercise/i,
  /to be continued/i,
  /TODO: .{0,50}later/i,
];

export function detectSilentDeferral(text: string): DeferralResult {
  const matched = DEFERRAL_PATTERNS.filter((p) => p.test(text)).map((p) =>
    p.toString(),
  );
  const detected = matched.length > 0;

  const result: DeferralResult = {
    detected,
    matchedPhrases: matched,
  };

  if (detected) {
    result.warningMessage = `Silent deferral detected (${matched.length} pattern(s)). Get explicit user consent before deferring tasks.`;
  }

  return result;
}

export interface TaskCompletionState {
  declaredTasks: string[];
  completedTasks: string[];
}

export interface TaskCompletionResult {
  blocked: boolean;
  incompleteTasks: string[];
  completionRatio: number;
  blockMessage?: string;
}

export function checkTaskCompletion(
  state: TaskCompletionState,
): TaskCompletionResult {
  const incomplete = state.declaredTasks.filter(
    (t) => !state.completedTasks.includes(t),
  );
  const completionRatio =
    state.declaredTasks.length === 0
      ? 1
      : state.completedTasks.length / state.declaredTasks.length;
  const blocked = incomplete.length > 0;

  const result: TaskCompletionResult = {
    blocked,
    incompleteTasks: incomplete,
    completionRatio,
  };

  if (blocked) {
    result.blockMessage = `${incomplete.length} task(s) uncompleted: ${incomplete
      .slice(0, 3)
      .join(
        ", ",
      )}${incomplete.length > 3 ? "..." : ""}. Complete or explicitly acknowledge with user consent.`;
  }

  return result;
}
