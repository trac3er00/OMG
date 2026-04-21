import type { HostType } from "../types/config.js";

export type ProviderStrength =
  | "code"
  | "analysis"
  | "research"
  | "vision"
  | "quick"
  | "private"
  | "code-review";

export type MultiForceProvider = HostType;

export interface MultiForceTask {
  readonly prompt: string;
  readonly intent?: ProviderStrength | readonly ProviderStrength[];
  readonly parallel?: boolean;
}

export interface ParallelDispatchProvider<T> {
  readonly name: MultiForceProvider;
  readonly dispatch: (task: MultiForceTask) => Promise<T>;
  readonly evaluate?: (result: T, task: MultiForceTask) => number;
}

export interface ParallelDispatchCandidate<T> {
  readonly provider: MultiForceProvider;
  readonly result: T;
  readonly score: number;
}

export interface ParallelDispatchResult<T> {
  readonly provider: MultiForceProvider;
  readonly result: T;
  readonly score: number;
  readonly candidates: readonly ParallelDispatchCandidate<T>[];
}

export const PROVIDER_STRENGTHS: Readonly<
  Partial<Record<MultiForceProvider, readonly ProviderStrength[]>>
> = {
  claude: ["code", "analysis"],
  gemini: ["research", "vision"],
  ollama: ["quick", "private"],
  "ollama-cloud": ["analysis", "quick", "code"],
  codex: ["code-review"],
};

const DEFAULT_PROVIDER_ORDER: readonly MultiForceProvider[] = [
  "claude",
  "gemini",
  "ollama",
  "ollama-cloud",
  "codex",
  "kimi",
  "opencode",
];

const CATEGORY_FALLBACKS: Readonly<
  Record<ProviderStrength, readonly MultiForceProvider[]>
> = {
  code: [
    "claude",
    "codex",
    "gemini",
    "kimi",
    "opencode",
    "ollama-cloud",
    "ollama",
  ],
  analysis: [
    "claude",
    "gemini",
    "codex",
    "kimi",
    "opencode",
    "ollama-cloud",
    "ollama",
  ],
  research: [
    "gemini",
    "claude",
    "codex",
    "kimi",
    "opencode",
    "ollama",
    "ollama-cloud",
  ],
  vision: [
    "gemini",
    "claude",
    "codex",
    "kimi",
    "opencode",
    "ollama",
    "ollama-cloud",
  ],
  quick: [
    "ollama",
    "ollama-cloud",
    "claude",
    "gemini",
    "codex",
    "kimi",
    "opencode",
  ],
  private: [
    "ollama",
    "claude",
    "gemini",
    "codex",
    "kimi",
    "opencode",
    "ollama-cloud",
  ],
  "code-review": [
    "codex",
    "claude",
    "gemini",
    "kimi",
    "opencode",
    "ollama",
    "ollama-cloud",
  ],
};

const SIGNAL_PATTERNS: Readonly<Record<ProviderStrength, readonly RegExp[]>> = {
  code: [
    /\b(code|implement|build|refactor|debug|fix|ship|component|api|backend)\b/i,
    /\btypescript\b/i,
    /\bjavascript\b/i,
  ],
  analysis: [
    /\b(analy[sz]e|analysis|audit|reason|architecture|explain|deep dive)\b/i,
  ],
  research: [
    /\b(research|investigate|compare|survey|study|report|tradeoffs?)\b/i,
  ],
  vision: [/\b(image|vision|screenshot|diagram|ocr|visual)\b/i],
  quick: [/\b(quick|trivial|tiny|simple|fast|minor|small|typo|one-liner)\b/i],
  private: [/\b(private|local|offline|air-gapped|on-device)\b/i],
  "code-review": [
    /\b(code review|review this diff|review this pr|review pull request)\b/i,
  ],
};

function normalizeTask(task: string | MultiForceTask): MultiForceTask {
  if (typeof task === "string") {
    return { prompt: task };
  }
  return task;
}

function uniqueIntents(task: MultiForceTask): ProviderStrength[] {
  const explicit =
    task.intent === undefined
      ? []
      : Array.isArray(task.intent)
        ? [...task.intent]
        : [task.intent];
  const inferred = inferIntents(task.prompt);
  const combined = [...explicit, ...inferred];
  return combined.filter((intent, index) => combined.indexOf(intent) === index);
}

function inferIntents(prompt: string): ProviderStrength[] {
  const intents: ProviderStrength[] = [];

  if (matchesAny(prompt, SIGNAL_PATTERNS["code-review"])) {
    intents.push("code-review");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.research)) {
    intents.push("research");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.vision)) {
    intents.push("vision");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.private)) {
    intents.push("private");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.quick)) {
    intents.push("quick");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.analysis)) {
    intents.push("analysis");
  }
  if (matchesAny(prompt, SIGNAL_PATTERNS.code)) {
    intents.push("code");
  }

  if (intents.length === 0) {
    intents.push("analysis");
  }

  return intents;
}

function matchesAny(prompt: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(prompt));
}

function scoreProviderForTask(
  provider: MultiForceProvider,
  task: MultiForceTask,
): number {
  const intents = uniqueIntents(task);
  const strengths = PROVIDER_STRENGTHS[provider] ?? [];
  let score = 0;

  intents.forEach((intent, intentIndex) => {
    const fallbackOrder = CATEGORY_FALLBACKS[intent];
    const fallbackIndex = fallbackOrder.indexOf(provider);
    const weight = Math.max(1, intents.length - intentIndex);

    if (strengths.includes(intent)) {
      score += 100 * weight;
    }

    if (fallbackIndex !== -1) {
      score += (fallbackOrder.length - fallbackIndex) * 10 * weight;
    }
  });

  const defaultIndex = DEFAULT_PROVIDER_ORDER.indexOf(provider);
  if (defaultIndex !== -1) {
    score += DEFAULT_PROVIDER_ORDER.length - defaultIndex;
  }

  return score;
}

export function routeToStrongest(
  task: string | MultiForceTask,
  availableProviders: readonly MultiForceProvider[],
): MultiForceProvider {
  if (availableProviders.length === 0) {
    throw new Error("routeToStrongest requires at least one provider");
  }

  const normalizedTask = normalizeTask(task);
  const [selected] = [...availableProviders].sort((left, right) => {
    const scoreDiff =
      scoreProviderForTask(right, normalizedTask) -
      scoreProviderForTask(left, normalizedTask);
    if (scoreDiff !== 0) {
      return scoreDiff;
    }
    return (
      DEFAULT_PROVIDER_ORDER.indexOf(left) -
      DEFAULT_PROVIDER_ORDER.indexOf(right)
    );
  });

  return selected;
}

function defaultResultScore<T>(
  provider: MultiForceProvider,
  task: MultiForceTask,
  result: T,
): number {
  if (typeof result === "object" && result !== null) {
    const scoreCandidate =
      "score" in result && typeof result.score === "number"
        ? result.score
        : "qualityScore" in result && typeof result.qualityScore === "number"
          ? result.qualityScore
          : undefined;
    if (scoreCandidate !== undefined) {
      return scoreCandidate;
    }
  }

  if (typeof result === "string") {
    return result.trim().length + scoreProviderForTask(provider, task);
  }

  return scoreProviderForTask(provider, task);
}

export async function parallelDispatch<T>(
  task: string | MultiForceTask,
  providers: readonly ParallelDispatchProvider<T>[],
): Promise<ParallelDispatchResult<T>> {
  if (providers.length === 0) {
    throw new Error("parallelDispatch requires at least one provider");
  }

  const normalizedTask = normalizeTask(task);
  const candidates = await Promise.all(
    providers.map(async (provider): Promise<ParallelDispatchCandidate<T>> => {
      const result = await provider.dispatch(normalizedTask);
      const score =
        provider.evaluate?.(result, normalizedTask) ??
        defaultResultScore(provider.name, normalizedTask, result);
      return {
        provider: provider.name,
        result,
        score,
      };
    }),
  );

  const preferredProvider = routeToStrongest(
    normalizedTask,
    providers.map((provider) => provider.name),
  );

  const [winner] = [...candidates].sort((left, right) => {
    if (right.score !== left.score) {
      return right.score - left.score;
    }
    if (left.provider === preferredProvider) {
      return -1;
    }
    if (right.provider === preferredProvider) {
      return 1;
    }
    return (
      DEFAULT_PROVIDER_ORDER.indexOf(left.provider) -
      DEFAULT_PROVIDER_ORDER.indexOf(right.provider)
    );
  });

  return {
    provider: winner.provider,
    result: winner.result,
    score: winner.score,
    candidates,
  };
}
