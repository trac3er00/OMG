export interface CompletionClaim {
  taskId: string;
  claimed: boolean;
  evidenceFiles?: string[];
  testsPassed?: boolean;
}

export interface ChecklistItem {
  id: string;
  required: boolean;
  completed: boolean;
  skippedReason?: string;
}

export interface EnforcementResult {
  approved: boolean;
  violations: string[];
  message?: string;
}

export function enforceCompletion(claim: CompletionClaim): EnforcementResult {
  const violations: string[] = [];

  if (
    claim.claimed &&
    (!claim.evidenceFiles || claim.evidenceFiles.length === 0)
  ) {
    violations.push(
      "no_evidence_for_claim: Completion claimed without evidence files",
    );
  }

  if (claim.claimed && claim.testsPassed === false) {
    violations.push(
      "tests_failing: Cannot claim completion when tests are failing",
    );
  }

  const message =
    violations.length > 0
      ? `Completion rejected: ${violations.join("; ")}`
      : undefined;
  return {
    approved: violations.length === 0,
    violations,
    ...(message ? { message } : {}),
  };
}

export function enforceChecklist(items: ChecklistItem[]): EnforcementResult {
  const violations: string[] = [];

  for (const item of items) {
    if (item.required && !item.completed && !item.skippedReason) {
      violations.push(
        `category_skip: Required item "${item.id}" skipped without reason`,
      );
    }
  }

  const message =
    violations.length > 0
      ? `Checklist incomplete: ${violations.length} item(s) skipped without reason`
      : undefined;

  return {
    approved: violations.length === 0,
    violations,
    ...(message ? { message } : {}),
  };
}
