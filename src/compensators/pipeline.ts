import { detectTrailingOff, type TaskItem } from "./trailing-off.js";
import {
  detectCourtesyCut,
  checkReadCompleteness,
  checkChecklistCompleteness,
} from "./completeness.js";
import {
  detectSilentDeferral,
  checkTaskCompletion,
  type TaskCompletionState,
} from "./deferral-tracker.js";
import { validateMerge, type AgentOutput } from "./merge-validator.js";
import {
  enforceCompletion,
  enforceChecklist,
  type CompletionClaim,
  type ChecklistItem,
} from "./completion-enforcer.js";

export interface CompensatorInput {
  taskItems?: TaskItem[];
  outputText?: string;
  readStats?: { totalLines: number; linesRead: number };
  taskState?: TaskCompletionState;
  agentOutputs?: AgentOutput[];
  claim?: CompletionClaim;
  checklistItems?: ChecklistItem[];
  checklistStats?: { totalItems: number; checkedItems: number };
}

export interface CompensatorCheckResult {
  name: string;
  passed: boolean;
  reason?: string;
}

export interface PipelineResult {
  verdict: "APPROVE" | "REJECT";
  checks: CompensatorCheckResult[];
  reasons: string[];
  timestamp: number;
}

export function evaluateWithCompensators(
  input: CompensatorInput,
): PipelineResult {
  const checks: CompensatorCheckResult[] = [];
  const reasons: string[] = [];

  if (input.taskItems && input.taskItems.length > 0) {
    const result = detectTrailingOff(input.taskItems);
    checks.push({
      name: "trailing_off",
      passed: !result.detected,
      ...(result.correctionMessage ? { reason: result.correctionMessage } : {}),
    });
    if (result.detected && result.correctionMessage) {
      reasons.push("trailing_off_detected");
      reasons.push(result.correctionMessage);
    }
  }

  if (input.readStats) {
    const result = checkReadCompleteness(
      input.readStats.totalLines,
      input.readStats.linesRead,
    );
    checks.push({
      name: "read_completeness",
      passed: !result.detected,
      ...(result.warningMessage ? { reason: result.warningMessage } : {}),
    });
    if (result.detected && result.warningMessage) {
      reasons.push("read_incomplete");
      reasons.push(result.warningMessage);
    }
  }

  if (input.checklistStats) {
    const result = checkChecklistCompleteness(
      input.checklistStats.totalItems,
      input.checklistStats.checkedItems,
    );
    checks.push({
      name: "checklist_completeness",
      passed: !result.detected,
      ...(result.warningMessage ? { reason: result.warningMessage } : {}),
    });
    if (result.detected && result.warningMessage) {
      reasons.push("checklist_incomplete");
      reasons.push(result.warningMessage);
    }
  }

  if (input.outputText) {
    const result = detectCourtesyCut(input.outputText);
    checks.push({
      name: "courtesy_cut",
      passed: !result.detected,
      ...(result.warningMessage ? { reason: result.warningMessage } : {}),
    });
    if (result.detected && result.warningMessage) {
      reasons.push("courtesy_cut_detected");
      reasons.push(result.warningMessage);
    }

    const deferResult = detectSilentDeferral(input.outputText);
    checks.push({
      name: "silent_deferral",
      passed: !deferResult.detected,
      ...(deferResult.warningMessage
        ? { reason: deferResult.warningMessage }
        : {}),
    });
    if (deferResult.detected && deferResult.warningMessage) {
      reasons.push("silent_deferral_detected");
      reasons.push(deferResult.warningMessage);
    }
  }

  if (input.taskState) {
    const result = checkTaskCompletion(input.taskState);
    checks.push({
      name: "task_completion",
      passed: !result.blocked,
      ...(result.blockMessage ? { reason: result.blockMessage } : {}),
    });
    if (result.blocked && result.blockMessage) {
      reasons.push("task_completion_blocked");
      reasons.push(result.blockMessage);
    }
  }

  if (input.agentOutputs && input.agentOutputs.length > 1) {
    const result = validateMerge(input.agentOutputs);
    checks.push({
      name: "merge_validation",
      passed: !result.hasContradiction,
      ...(result.warningMessage ? { reason: result.warningMessage } : {}),
    });
    if (result.hasContradiction && result.warningMessage) {
      reasons.push("merge_contradiction_detected");
      reasons.push(result.warningMessage);
    }
  }

  if (input.claim) {
    const result = enforceCompletion(input.claim);
    checks.push({
      name: "completion_claim",
      passed: result.approved,
      ...(result.message ? { reason: result.message } : {}),
    });
    if (!result.approved && result.message) {
      reasons.push("completion_claim_rejected");
      reasons.push(result.message);
    }
  }

  if (input.checklistItems) {
    const result = enforceChecklist(input.checklistItems);
    checks.push({
      name: "checklist_enforcement",
      passed: result.approved,
      ...(result.message ? { reason: result.message } : {}),
    });
    if (!result.approved && result.message) {
      reasons.push("checklist_enforcement_failed");
      reasons.push(result.message);
    }
  }

  const allPassed = checks.every((check) => check.passed);

  return {
    verdict: allPassed ? "APPROVE" : "REJECT",
    checks,
    reasons,
    timestamp: Date.now(),
  };
}
