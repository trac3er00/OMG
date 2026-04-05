// Ported from runtime/decision_engine.py

import type {
  AgentRecommendation,
  TaskComplexity,
} from "../interfaces/orchestration.js";

// ---------------------------------------------------------------------------
// Complexity indicators — regex patterns per complexity level
// ---------------------------------------------------------------------------

const COMPLEXITY_INDICATORS: ReadonlyMap<TaskComplexity, readonly RegExp[]> =
  new Map<TaskComplexity, readonly RegExp[]>([
    [
      "trivial",
      [/typo/i, /fix\s*spelling/i, /rename\s*file/i, /change\s*label/i],
    ],
    [
      "simple",
      [/\bsimple\b/i, /\bquick\b/i, /\bminor\b/i, /\bsmall\b/i, /add\s*comment/i],
    ],
    [
      "moderate",
      [/\bimplement\b/i, /add\s*feature/i, /\brefactor\b/i, /fix\s*bug/i],
    ],
    [
      "complex",
      [
        /design\s*system/i,
        /\barchitecture\b/i,
        /multi\s*agent/i,
        /\bparallel\b/i,
        /security\s*audit/i,
        /performance\s*optim/i,
        /\bOAuth\b/i,
        /\bauth\s*system\b/i,
      ],
    ],
    [
      "extreme",
      [
        /\bredesign\b/i,
        /rewrite\s*entire/i,
        /machine\s*learning/i,
        /novel\s*algorithm/i,
        /research\s*new/i,
      ],
    ],
  ]);

// ---------------------------------------------------------------------------
// Domain → agent mapping
// ---------------------------------------------------------------------------

interface DomainEntry {
  readonly keywords: ReadonlySet<string>;
  readonly agent: string;
  readonly category: string;
}

const DOMAIN_AGENT_MAP: readonly DomainEntry[] = [
  {
    keywords: new Set([
      "ui",
      "ux",
      "css",
      "visual",
      "design",
      "frontend",
      "component",
    ]),
    agent: "frontend-designer",
    category: "visual-engineering",
  },
  {
    keywords: new Set(["api", "rest", "graphql", "endpoint", "contract"]),
    agent: "api-builder",
    category: "deep",
  },
  {
    keywords: new Set(["security", "auth", "vulnerability", "audit"]),
    agent: "security-auditor",
    category: "ultrabrain",
  },
  {
    keywords: new Set(["database", "sql", "migration", "schema"]),
    agent: "database-engineer",
    category: "deep",
  },
  {
    keywords: new Set(["test", "spec", "coverage", "e2e"]),
    agent: "testing-engineer",
    category: "quick",
  },
  {
    keywords: new Set(["deploy", "docker", "kubernetes", "ci", "cd", "infra"]),
    agent: "infra-engineer",
    category: "deep",
  },
  {
    keywords: new Set(["code", "codex", "implement", "build", "develop"]),
    agent: "codex",
    category: "deep",
  },
  {
    keywords: new Set(["research", "gemini", "analyze", "investigate"]),
    agent: "gemini",
    category: "ultrabrain",
  },
] as const;

// ---------------------------------------------------------------------------
// Provider priority by category
// ---------------------------------------------------------------------------

const CATEGORY_PROVIDER_MAP: Readonly<Record<string, readonly string[]>> = {
  "visual-engineering": ["gemini", "claude"],
  deep: ["codex", "claude"],
  ultrabrain: ["codex", "claude"],
  quick: ["claude", "opencode"],
};

const DEFAULT_PROVIDER = "claude";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Falls back to `"moderate"` when no indicator pattern matches. */
export function scoreComplexity(task: string): TaskComplexity {
  for (const [complexity, patterns] of COMPLEXITY_INDICATORS) {
    for (const pattern of patterns) {
      if (pattern.test(task)) {
        return complexity;
      }
    }
  }
  return "moderate";
}

function extractDomain(
  prompt: string,
): { agent: string; category: string } | undefined {
  const words = new Set(prompt.toLowerCase().match(/\b\w+\b/g) ?? []);

  for (const entry of DOMAIN_AGENT_MAP) {
    for (const keyword of entry.keywords) {
      if (words.has(keyword)) {
        return { agent: entry.agent, category: entry.category };
      }
    }
  }
  return undefined;
}

function selectProvider(category: string): string {
  const candidates = CATEGORY_PROVIDER_MAP[category];
  if (candidates && candidates.length > 0) {
    return candidates[0] ?? DEFAULT_PROVIDER;
  }
  return DEFAULT_PROVIDER;
}

function buildFallback(primary: string): readonly string[] {
  const all = ["claude", "codex", "gemini", "opencode"];
  return all.filter((p) => p !== primary);
}

export function recommendAgent(task: string): AgentRecommendation {
  const complexity = scoreComplexity(task);
  const domain = extractDomain(task);

  const agentName = domain?.agent ?? "task";
  const category = domain?.category ?? "unspecified-high";
  const provider = selectProvider(category);

  let confidence = 0.5;
  if (domain) {
    confidence += 0.3;
  }
  if (complexity === "trivial" || complexity === "simple") {
    confidence += 0.1;
  }

  const fallback = buildFallback(provider);
  const reasoning = `Complexity=${complexity}, Domain=${agentName}, Provider=${provider}`;

  return {
    agentName,
    category,
    provider,
    confidence,
    fallback,
    reasoning,
    complexity,
  };
}
