import { join } from "node:path";
import { appendJsonLine } from "../state/atomic-io.js";
import { classify } from "../classifier/index.js";
import { understandIntent, type IntentDomain } from "./index.js";

export interface FidelityContext {
  goal: string;
  history?: string[];
  round?: number;
}

export interface FidelityResult {
  needsClarification: boolean;
  clarificationQuestion: string | null;
  interpretation: string;
  gapChecks: string[];
  canProceed: boolean;
  round: number;
}

interface GapAssessment {
  kind: "scope" | "expectation" | "constraint";
  severity: number;
  significant: boolean;
  summary: string;
  question: string;
}

const MAX_CLARIFICATION_ROUNDS = 3;
const TRIVIAL_WORD_LIMIT = 5;

const SIMPLE_CRUD_ACTIONS = new Set([
  "add",
  "change",
  "create",
  "delete",
  "fix",
  "get",
  "list",
  "remove",
  "rename",
  "update",
]);

const VAGUE_TERMS = new Set([
  "anything",
  "everything",
  "it",
  "something",
  "stuff",
  "that",
  "thing",
  "things",
  "this",
]);

const DELIVERABLE_KEYWORDS = [
  /\bapi\b/u,
  /\bapp\b/u,
  /\bauth\b/u,
  /\bbutton\b/u,
  /\bcli\b/u,
  /\bcomponent\b/u,
  /\bdashboard\b/u,
  /\bdeployment\b/u,
  /\bdocs?\b/u,
  /\bendpoint\b/u,
  /\bfeature\b/u,
  /\bflow\b/u,
  /\bform\b/u,
  /\bguide\b/u,
  /\bhook\b/u,
  /\blanding page\b/u,
  /\bmodule\b/u,
  /\bpage\b/u,
  /\bpipeline\b/u,
  /\bscript\b/u,
  /\bservice\b/u,
  /\bsystem\b/u,
  /\btable\b/u,
  /\bworkflow\b/u,
];

const CONSTRAINT_MARKERS = [
  /\bavoid\b/u,
  /\bbun\b/u,
  /\bcurrent\b/u,
  /\bdon't\b/u,
  /\bexisting\b/u,
  /\bkeep\b/u,
  /\bmust\b/u,
  /\bno\b/u,
  /\bonly\b/u,
  /\breact\b/u,
  /\bstay\b/u,
  /\btypescript\b/u,
  /\bwithout\b/u,
  /\bwithin\b/u,
];

const BROAD_ACTIONS = new Set([
  "build",
  "do",
  "fix",
  "handle",
  "improve",
  "make",
  "optimize",
  "update",
]);

function normalizeGoal(goal: string): string {
  return goal.trim().replace(/\s+/gu, " ");
}

function countWords(goal: string): number {
  return normalizeGoal(goal).split(" ").filter(Boolean).length;
}

function tokenize(goal: string): string[] {
  return normalizeGoal(goal).toLowerCase().split(/\s+/u).filter(Boolean);
}

function hasPattern(goal: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(goal));
}

function hasVagueTerm(goal: string): boolean {
  return tokenize(goal).some((word) => VAGUE_TERMS.has(word));
}

function hasDeliverable(goal: string): boolean {
  return hasPattern(goal.toLowerCase(), DELIVERABLE_KEYWORDS);
}

function hasConstraintSignal(goal: string): boolean {
  return hasPattern(goal.toLowerCase(), CONSTRAINT_MARKERS);
}

function isTrivialGoal(goal: string): boolean {
  const words = tokenize(goal);
  const firstWord = words[0];
  if (!firstWord) {
    return false;
  }

  return (
    words.length < TRIVIAL_WORD_LIMIT &&
    SIMPLE_CRUD_ACTIONS.has(firstWord) &&
    !hasVagueTerm(goal)
  );
}

function formatInterpretation(goal: string): string {
  const normalizedGoal = normalizeGoal(goal);
  if (!normalizedGoal) {
    return "Interpretation: the user has not provided a concrete task yet.";
  }

  const intent = understandIntent(normalizedGoal);
  const classification = classify(normalizedGoal);
  const domainDetail = intent.domain === "other" ? "general" : intent.domain;

  return `Interpretation: treat this as a ${classification.intent} request in the ${domainDetail} domain aimed at ${normalizedGoal.toLowerCase()}.`;
}

function buildScopeGap(goal: string): GapAssessment {
  const normalizedGoal = normalizeGoal(goal).toLowerCase();
  const intent = understandIntent(normalizedGoal);
  const classification = classify(normalizedGoal);
  const words = countWords(normalizedGoal);
  let severity = 0;

  if (!normalizedGoal) {
    severity += 4;
  }
  if (hasVagueTerm(normalizedGoal)) {
    severity += 3;
  }
  if (words <= 3) {
    severity += 2;
  }
  if (intent.domain === "other" && !hasDeliverable(normalizedGoal)) {
    severity += 2;
  }
  if (classification.confidence < 0.7) {
    severity += 1;
  }

  const significant = severity >= 3;
  return {
    kind: "scope",
    severity,
    significant,
    summary: significant
      ? "Significant scope gap: the target artifact or surface is not concrete enough yet."
      : "Scope gap is minor: the target surface is specific enough to start.",
    question: buildScopeQuestion(intent.domain),
  };
}

function buildExpectationGap(goal: string): GapAssessment {
  const normalizedGoal = normalizeGoal(goal).toLowerCase();
  const intent = understandIntent(normalizedGoal);
  const words = tokenize(normalizedGoal);
  const firstWord = words[0] ?? "";
  let severity = 0;

  if (!normalizedGoal) {
    severity += 4;
  }
  if (BROAD_ACTIONS.has(firstWord)) {
    severity += 1;
  }
  if (!hasDeliverable(normalizedGoal)) {
    severity += 2;
  }
  if (
    !hasDeliverable(normalizedGoal) &&
    intent.ambiguities.some((item) => item.includes("expected outcome"))
  ) {
    severity += 2;
  }
  if (countWords(normalizedGoal) <= 4) {
    severity += 1;
  }

  const significant = severity >= 3;
  return {
    kind: "expectation",
    severity,
    significant,
    summary: significant
      ? "Significant expectation gap: success criteria are still too vague to verify cleanly."
      : "Expectation gap is minor: success looks concrete enough to evaluate.",
    question: buildExpectationQuestion(intent.domain),
  };
}

function buildConstraintGap(goal: string): GapAssessment {
  const normalizedGoal = normalizeGoal(goal).toLowerCase();
  const intent = understandIntent(normalizedGoal);
  const classification = classify(normalizedGoal);
  let severity = 0;

  if (!hasConstraintSignal(normalizedGoal)) {
    if (["security", "infrastructure", "data"].includes(intent.domain)) {
      severity += 2;
    }
    if (["high", "critical"].includes(classification.risk)) {
      severity += 2;
    }
    if (["hard", "expert"].includes(classification.complexity)) {
      severity += 1;
    }
  }

  const significant = severity >= 3;
  return {
    kind: "constraint",
    severity,
    significant,
    summary: significant
      ? "Significant constraint gap: guardrails are missing for a higher-risk request."
      : "Constraint gap is minor: there is enough room to proceed with a conservative default.",
    question: buildConstraintQuestion(intent.domain),
  };
}

function buildScopeQuestion(domain: IntentDomain): string {
  switch (domain) {
    case "frontend":
      return "Which specific screen or component should this change target?";
    case "backend":
      return "Which specific endpoint or service should this change target?";
    case "infrastructure":
      return "Which specific environment or deployment surface should this change target?";
    case "data":
      return "Which specific table, schema, or pipeline should this change target?";
    case "security":
      return "Which specific auth or permission surface should this change target?";
    case "documentation":
      return "Which specific document or guide should this change target?";
    default:
      return "Which specific deliverable should I produce: UI, API, automation, documentation, or refactor?";
  }
}

function buildExpectationQuestion(domain: IntentDomain): string {
  switch (domain) {
    case "frontend":
      return "Should success mean a new page, a component update, or a styling change?";
    case "backend":
      return "Should success mean a new endpoint, a behavior change, or a bug fix?";
    case "documentation":
      return "Should success mean a new guide, a wording update, or an API explanation?";
    default:
      return "What single outcome should count as done: new feature, bug fix, refactor, or analysis?";
  }
}

function buildConstraintQuestion(domain: IntentDomain): string {
  switch (domain) {
    case "security":
      return "Should this stay non-breaking in the current auth flow, or can it change the auth architecture?";
    case "infrastructure":
      return "Should this stay within the current platform, or can it change deployment tooling?";
    case "data":
      return "Should this stay backward-compatible with the current schema, or is a breaking migration allowed?";
    default:
      return "Should I stay within the current stack and file boundaries, or is a broader refactor allowed?";
  }
}

function getGapLogPath(): string {
  return join(process.cwd(), ".omg", "intent", "gaps.jsonl");
}

function logGapEvent(context: FidelityContext, result: FidelityResult): void {
  const analysis = understandIntent(context.goal);
  const classification = classify(context.goal);

  appendJsonLine(getGapLogPath(), {
    timestamp: new Date().toISOString(),
    goal: context.goal,
    round: result.round,
    history: context.history ?? [],
    interpretation: result.interpretation,
    gapChecks: result.gapChecks,
    clarificationQuestion: result.clarificationQuestion,
    analysis: {
      intent: analysis.intent,
      domain: analysis.domain,
      confidenceScore: analysis.confidenceScore,
      ambiguities: analysis.ambiguities,
    },
    classification,
  });
}

function selectQuestion(
  gaps: readonly GapAssessment[],
  round: number,
): string | null {
  const significantGaps = gaps
    .filter((gap) => gap.significant)
    .sort((left, right) => right.severity - left.severity);

  const selectedGap = significantGaps[round];
  return selectedGap?.question ?? null;
}

function buildGapChecks(gaps: readonly GapAssessment[]): string[] {
  return gaps.map((gap) => `${gap.kind}: ${gap.summary}`);
}

function evaluateFidelity(
  context: FidelityContext,
  shouldLog: boolean,
): FidelityResult {
  const normalizedGoal = normalizeGoal(context.goal);
  const round = Math.max(context.round ?? context.history?.length ?? 0, 0);
  const interpretation = formatInterpretation(normalizedGoal);
  const gaps = [
    buildScopeGap(normalizedGoal),
    buildExpectationGap(normalizedGoal),
    buildConstraintGap(normalizedGoal),
  ] as const;
  const gapChecks = buildGapChecks(gaps);

  if (isTrivialGoal(normalizedGoal)) {
    return {
      needsClarification: false,
      clarificationQuestion: null,
      interpretation,
      gapChecks,
      canProceed: true,
      round,
    };
  }

  if (round >= MAX_CLARIFICATION_ROUNDS) {
    return {
      needsClarification: false,
      clarificationQuestion: null,
      interpretation,
      gapChecks,
      canProceed: true,
      round,
    };
  }

  const clarificationQuestion = selectQuestion(gaps, round);
  const result: FidelityResult = {
    needsClarification: clarificationQuestion !== null,
    clarificationQuestion,
    interpretation,
    gapChecks,
    canProceed: clarificationQuestion === null,
    round,
  };

  if (shouldLog && result.needsClarification) {
    logGapEvent(context, result);
  }

  return result;
}

export class FidelityChecker {
  check(context: FidelityContext): FidelityResult {
    return checkFidelity(context);
  }

  shouldClarify(goal: string): boolean {
    return shouldClarify(goal);
  }
}

export function shouldClarify(goal: string): boolean {
  return evaluateFidelity({ goal }, false).needsClarification;
}

export function checkFidelity(context: FidelityContext): FidelityResult {
  return evaluateFidelity(context, true);
}
