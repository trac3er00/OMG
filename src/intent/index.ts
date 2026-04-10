import type { UssProfile, UserSessionServices } from "../state/uss.js";

export type IntentType =
  | "trivial"
  | "simple"
  | "moderate"
  | "complex"
  | "architectural"
  | "research";

export type IntentDomain =
  | "frontend"
  | "backend"
  | "infrastructure"
  | "data"
  | "security"
  | "documentation"
  | "other";

export type EffortLevel = "low" | "medium" | "high";
export type RiskLevel = "low" | "medium" | "high";

export interface IntentComplexity {
  readonly filesAffected: number;
  readonly effort: EffortLevel;
  readonly riskLevel: RiskLevel;
  readonly signals: readonly string[];
}

export interface IntentAnalysis {
  readonly intent: IntentType;
  readonly domain: IntentDomain;
  readonly complexity: IntentComplexity;
  readonly ambiguities: readonly string[];
  readonly suggestedApproach: string;
  readonly clarifyingQuestions: readonly string[];
}

export interface IntentOptions {
  readonly uss?: Pick<UserSessionServices, "getProfile" | "suggestApproach">;
}

const DOMAIN_KEYWORDS: Readonly<Record<IntentDomain, readonly string[]>> = {
  frontend: [
    "ui",
    "ux",
    "button",
    "form",
    "modal",
    "page",
    "layout",
    "css",
    "html",
    "react",
    "frontend",
    "component",
    "login",
    "dashboard",
    "table",
    "admin",
  ],
  backend: [
    "api",
    "endpoint",
    "server",
    "backend",
    "service",
    "controller",
    "route",
    "database",
    "queue",
    "worker",
    "webhook",
  ],
  infrastructure: [
    "infra",
    "infrastructure",
    "deploy",
    "deployment",
    "docker",
    "kubernetes",
    "terraform",
    "helm",
    "pipeline",
    "ci",
    "cdn",
    "hosting",
  ],
  data: [
    "data",
    "analytics",
    "etl",
    "warehouse",
    "schema",
    "sql",
    "query",
    "migration",
    "reporting",
  ],
  security: [
    "auth",
    "authentication",
    "authorization",
    "security",
    "permission",
    "secret",
    "token",
    "credential",
    "oauth",
    "jwt",
    "encrypt",
    "encryption",
    "compliance",
  ],
  documentation: [
    "docs",
    "documentation",
    "readme",
    "comment",
    "guide",
    "typo",
    "copy",
    "wording",
    "spell",
  ],
  other: [],
};

const TRIVIAL_PATTERNS = [/\bfix typo\b/, /\btypo\b/, /\brename\b/, /\bcopy\b/];
const SIMPLE_PATTERNS = [/\bupdate\b/, /\bchange\b/, /\badjust\b/, /\badd\b/];
const MODERATE_PATTERNS = [
  /\bimplement\b/,
  /\bcreate\b/,
  /\bbuild\b/,
  /\brefactor\b/,
  /\bintegrate\b/,
  /\bpagination\b/,
  /\bretry\b/,
  /\bvalidation\b/,
  /\brotation\b/,
];
const COMPLEX_PATTERNS = [
  /\bend-to-end\b/,
  /\bmulti-step\b/,
  /\bfull[- ]stack\b/,
  /\bmigrate\b/,
  /\boverhaul\b/,
];
const ARCHITECTURAL_PATTERNS = [
  /\bredesign\b/,
  /\bre-architect\b/,
  /\barchitecture\b/,
  /\bplatform\b/,
  /\bsystem\b/,
  /\bframework\b/,
];
const RESEARCH_PATTERNS = [
  /\bresearch\b/,
  /\binvestigate\b/,
  /\banaly[sz]e\b/,
  /\bcompare\b/,
  /\bevaluate\b/,
  /\bstudy\b/,
  /\bsurvey\b/,
];

const VAGUE_TERMS = [
  "something",
  "stuff",
  "thing",
  "things",
  "it",
  "this",
  "that",
];
const VAGUE_ACTIONS = ["do", "fix", "handle", "improve", "update", "make"];
const BROAD_OBJECTS = [
  "system",
  "api",
  "backend",
  "frontend",
  "app",
  "codebase",
];

function normalizePrompt(prompt: string): string {
  return prompt.trim().toLowerCase().replace(/\s+/g, " ");
}

function countWords(prompt: string): number {
  return prompt.trim().split(/\s+/).filter(Boolean).length;
}

function hasAnyPattern(prompt: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(prompt));
}

function scoreDomain(prompt: string, domain: IntentDomain): number {
  if (domain === "other") {
    return 0;
  }

  return DOMAIN_KEYWORDS[domain].reduce((score, keyword) => {
    return score + (prompt.includes(keyword) ? 1 : 0);
  }, 0);
}

function detectDomain(prompt: string): IntentDomain {
  const scored = (Object.keys(DOMAIN_KEYWORDS) as IntentDomain[])
    .filter((domain) => domain !== "other")
    .map((domain) => ({ domain, score: scoreDomain(prompt, domain) }))
    .sort((left, right) => right.score - left.score);

  const winner = scored[0];
  return winner && winner.score > 0 ? winner.domain : "other";
}

function detectAmbiguities(prompt: string, domain: IntentDomain): string[] {
  const ambiguities: string[] = [];
  const words = prompt.split(" ");
  const firstWord = words[0] ?? "";

  if (words.length <= 2) {
    ambiguities.push(
      "Prompt is very short and may be missing scope or acceptance criteria.",
    );
  }

  if (VAGUE_TERMS.some((term) => prompt.includes(term))) {
    ambiguities.push(
      "Prompt uses vague nouns instead of a concrete task target.",
    );
  }

  if (
    VAGUE_ACTIONS.includes(firstWord) &&
    !prompt.includes(" in ") &&
    !prompt.includes(" on ")
  ) {
    ambiguities.push(
      "Primary action verb is broad and does not describe the expected outcome precisely.",
    );
  }

  if (domain === "other") {
    ambiguities.push("No strong domain signal was detected.");
  }

  if (
    BROAD_OBJECTS.some((term) => prompt.includes(term)) &&
    !hasAnyPattern(prompt, ARCHITECTURAL_PATTERNS) &&
    words.length < 6
  ) {
    ambiguities.push(
      "Target area is broad, but the requested scope is not bounded.",
    );
  }

  return [...new Set(ambiguities)];
}

function detectIntent(
  prompt: string,
  wordCount: number,
  ambiguities: readonly string[],
): IntentType {
  if (hasAnyPattern(prompt, RESEARCH_PATTERNS)) {
    return "research";
  }
  if (hasAnyPattern(prompt, ARCHITECTURAL_PATTERNS)) {
    return "architectural";
  }
  if (hasAnyPattern(prompt, COMPLEX_PATTERNS) || wordCount >= 16) {
    return "complex";
  }
  if (hasAnyPattern(prompt, MODERATE_PATTERNS) || wordCount >= 8) {
    return "moderate";
  }
  if (hasAnyPattern(prompt, TRIVIAL_PATTERNS)) {
    return ambiguities.length === 0 ? "trivial" : "simple";
  }
  if (hasAnyPattern(prompt, SIMPLE_PATTERNS) || ambiguities.length > 0) {
    return "simple";
  }
  return wordCount <= 4 ? "trivial" : "simple";
}

function estimateFilesAffected(
  intent: IntentType,
  domain: IntentDomain,
): number {
  if (intent === "architectural") {
    return domain === "security" || domain === "infrastructure" ? 12 : 9;
  }
  if (intent === "research") {
    return 0;
  }
  if (intent === "complex") {
    return 6;
  }
  if (intent === "moderate") {
    return 3;
  }
  if (intent === "simple") {
    return 2;
  }
  return 1;
}

function estimateEffort(intent: IntentType): EffortLevel {
  if (
    intent === "architectural" ||
    intent === "complex" ||
    intent === "research"
  ) {
    return "high";
  }
  if (intent === "moderate") {
    return "medium";
  }
  return "low";
}

function estimateRisk(intent: IntentType, domain: IntentDomain): RiskLevel {
  if (domain === "security" || domain === "infrastructure") {
    return intent === "trivial" ? "medium" : "high";
  }
  if (intent === "architectural" || intent === "complex") {
    return "high";
  }
  if (intent === "moderate") {
    return "medium";
  }
  return "low";
}

function buildClarifyingQuestions(
  ambiguities: readonly string[],
  domain: IntentDomain,
  prompt: string,
): string[] {
  if (ambiguities.length === 0) {
    return [];
  }

  const questions = [
    "What exact outcome should change when this task is complete?",
    "Which file, component, endpoint, or subsystem should be touched?",
  ];

  if (domain === "backend" || prompt.includes("api")) {
    questions.push(
      "Which API endpoint or contract should be updated, and how should its behavior change?",
    );
  }
  if (domain === "frontend") {
    questions.push(
      "Which screen or component should be updated, and what user-visible behavior should change?",
    );
  }
  if (domain === "security") {
    questions.push(
      "What security property should improve: authentication, authorization, secret handling, or auditability?",
    );
  }
  if (domain === "other") {
    questions.push(
      "Is this primarily a frontend, backend, infrastructure, data, security, or documentation task?",
    );
  }

  return questions;
}

function buildSignals(
  prompt: string,
  intent: IntentType,
  domain: IntentDomain,
  ambiguities: readonly string[],
): string[] {
  const signals = [`intent:${intent}`, `domain:${domain}`];
  if (countWords(prompt) >= 12) {
    signals.push("long-prompt");
  }
  if (ambiguities.length > 0) {
    signals.push("ambiguous");
  }
  if (hasAnyPattern(prompt, ARCHITECTURAL_PATTERNS)) {
    signals.push("architecture-signal");
  }
  if (hasAnyPattern(prompt, RESEARCH_PATTERNS)) {
    signals.push("research-signal");
  }
  return signals;
}

function describeProfile(profile: UssProfile): string {
  if (profile.technicalLevel === "beginner") {
    return "Prefer a step-by-step explanation with minimal jargon.";
  }
  if (profile.technicalLevel === "advanced") {
    return "Emphasize tradeoffs, constraints, and optimization opportunities.";
  }
  return "Balance clarity with implementation detail.";
}

function buildSuggestedApproach(
  prompt: string,
  intent: IntentType,
  domain: IntentDomain,
  ambiguities: readonly string[],
  uss?: Pick<UserSessionServices, "getProfile" | "suggestApproach">,
): string {
  const baseTask = `${intent} ${domain} task: ${prompt}`;
  const profileLead = uss ? describeProfile(uss.getProfile()) : "";
  const ambiguityLead =
    ambiguities.length > 0
      ? "Resolve the ambiguities before implementation, then continue with the narrowed scope."
      : intent === "architectural"
        ? "Start with boundaries, dependencies, and migration risk before proposing changes."
        : intent === "research"
          ? "Gather constraints, compare options, and summarize tradeoffs before implementation."
          : "Proceed with the smallest validated change that satisfies the request.";
  const ussSuggestion = uss
    ? uss.suggestApproach(baseTask)
    : `Explain the plan for this ${domain} task in clear terms and keep risk proportional to a ${intent} request.`;

  return [ambiguityLead, profileLead, ussSuggestion].filter(Boolean).join(" ");
}

export function understandIntent(
  rawPrompt: string,
  options: IntentOptions = {},
): IntentAnalysis {
  const prompt = normalizePrompt(rawPrompt);
  const wordCount = countWords(prompt);
  const domain = detectDomain(prompt);
  const ambiguities = detectAmbiguities(prompt, domain);
  const intent = detectIntent(prompt, wordCount, ambiguities);

  return {
    intent,
    domain,
    complexity: {
      filesAffected: estimateFilesAffected(intent, domain),
      effort: estimateEffort(intent),
      riskLevel: estimateRisk(intent, domain),
      signals: buildSignals(prompt, intent, domain, ambiguities),
    },
    ambiguities,
    suggestedApproach: buildSuggestedApproach(
      prompt,
      intent,
      domain,
      ambiguities,
      options.uss,
    ),
    clarifyingQuestions: buildClarifyingQuestions(ambiguities, domain, prompt),
  };
}
