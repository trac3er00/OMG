/**
 * TaskClassifier Types and Interfaces
 *
 * Type definitions for the task classification system that categorizes
 * tasks by intent, risk level, and complexity to enable appropriate routing
 * and governance decisions.
 */

/**
 * Intent of the task - describes the primary purpose of the work being performed.
 */
export type TaskIntent = "build" | "modify" | "refactor" | "investigate" | "deploy" | "secure" | "handoff";

/**
 * Risk level of the task - indicates potential impact if the task is executed incorrectly.
 */
export type TaskRisk = "low" | "medium" | "high" | "critical";

/**
 * Complexity of the task - reflects the technical difficulty and scope of work.
 */
export type TaskComplexity = "simple" | "moderate" | "hard" | "expert";

/**
 * Valid task intents for type guard validation.
 */
const TASK_INTENTS: readonly TaskIntent[] = ["build", "modify", "refactor", "investigate", "deploy", "secure", "handoff"];

/**
 * Valid task risks for type guard validation.
 */
const TASK_RISKS: readonly TaskRisk[] = ["low", "medium", "high", "critical"];

/**
 * Valid task complexities for type guard validation.
 */
const TASK_COMPLEXITIES: readonly TaskComplexity[] = ["simple", "moderate", "hard", "expert"];

/**
 * Result of classifying a task - contains the classification outcomes and supporting evidence.
 */
export interface ClassificationResult {
  /** The primary intent of the task */
  intent: TaskIntent;
  /** The risk level associated with the task */
  risk: TaskRisk;
  /** The complexity level of the task */
  complexity: TaskComplexity;
  /** Confidence score between 0 and 1 indicating classification certainty */
  confidence: number;
  /** List of matched signal names that contributed to the classification */
  signals: string[];
  /** Optional human-readable explanation of the classification decision */
  reasoning?: string;
}

/**
 * Type guard: checks if a value is a valid TaskIntent.
 *
 * @param v - The value to check
 * @returns True if the value is a valid TaskIntent, false otherwise
 */
export function isTaskIntent(v: unknown): v is TaskIntent {
  return typeof v === "string" && TASK_INTENTS.includes(v as TaskIntent);
}

/**
 * Type guard: checks if a value is a valid TaskRisk.
 *
 * @param v - The value to check
 * @returns True if the value is a valid TaskRisk, false otherwise
 */
export function isTaskRisk(v: unknown): v is TaskRisk {
  return typeof v === "string" && TASK_RISKS.includes(v as TaskRisk);
}

/**
 * Type guard: checks if a value is a valid TaskComplexity.
 *
 * @param v - The value to check
 * @returns True if the value is a valid TaskComplexity, false otherwise
 */
export function isTaskComplexity(v: unknown): v is TaskComplexity {
  return typeof v === "string" && TASK_COMPLEXITIES.includes(v as TaskComplexity);
}

/**
 * Type guard: checks if a value is a valid ClassificationResult.
 *
 * @param v - The value to check
 * @returns True if the value is a valid ClassificationResult, false otherwise
 */
export function isClassificationResult(v: unknown): v is ClassificationResult {
  if (typeof v !== "object" || v === null) {
    return false;
  }

  const obj = v as Record<string, unknown>;

  // Check required fields exist with correct types
  if (!isTaskIntent(obj.intent)) {
    return false;
  }
  if (!isTaskRisk(obj.risk)) {
    return false;
  }
  if (!isTaskComplexity(obj.complexity)) {
    return false;
  }
  if (typeof obj.confidence !== "number") {
    return false;
  }
  if (obj.confidence < 0 || obj.confidence > 1) {
    return false;
  }
  if (!Array.isArray(obj.signals)) {
    return false;
  }
  // All signals should be strings (but we don't validate signal content)
  if (!obj.signals.every((s) => typeof s === "string")) {
    return false;
  }
  // Optional reasoning must be a string if present
  if (obj.reasoning !== undefined && typeof obj.reasoning !== "string") {
    return false;
  }

  return true;
}
