import type {
  ClassificationResult,
  TaskComplexity,
  TaskIntent,
  TaskRisk,
} from "./types.js";

interface IntentSignal {
  intent: TaskIntent;
  label: string;
  pattern: RegExp;
}

interface RiskSignal {
  risk: TaskRisk;
  label: string;
  pattern: RegExp;
}

interface ComplexitySignal {
  complexity: TaskComplexity;
  label: string;
  pattern: RegExp;
  weight: number;
}

const DEFAULT_INTENT: TaskIntent = "build";
const DEFAULT_RISK: TaskRisk = "low";
const DEFAULT_COMPLEXITY: TaskComplexity = "simple";

const INTENT_SIGNALS: readonly IntentSignal[] = [
  {
    intent: "build",
    label: "build",
    pattern: /\bbuild\b|\bcreate\b|\bmake\b|\bgenerate\b|\bscaffold\b|\badd\b/i,
  },
  {
    intent: "modify",
    label: "modify",
    pattern: /\bmodify\b|\bupdate\b|\bchange\b|\bedit\b|\bfix\b|\bpatch\b/i,
  },
  {
    intent: "refactor",
    label: "refactor",
    pattern:
      /\brefactor\b|\brestructure\b|\breorganize\b|\bclean\b|\bimprove\b/i,
  },
  {
    intent: "investigate",
    label: "investigate",
    pattern:
      /\binvestigate\b|\banaly[sz]e\b|\bdebug\b|\bdiagnose\b|\bresearch\b|\bfind\b/i,
  },
  {
    intent: "deploy",
    label: "deploy",
    pattern: /\bdeploy\b|\brelease\b|\bpublish\b|\bship\b|\blaunch\b/i,
  },
  {
    intent: "secure",
    label: "secure",
    pattern: /\bsecure\b|\baudit\b|\bharden\b|\bprotect\b|\bencrypt\b/i,
  },
  {
    intent: "handoff",
    label: "handoff",
    pattern: /\bhandoff\b|\bdocument\b|\bsummarize\b|\breport\b/i,
  },
];

const DESTRUCTIVE_INTENT_SIGNAL: IntentSignal = {
  intent: "modify",
  label: "modify",
  pattern: /\bdelete\b|\bremove\b|\bdrop\b|\bdestroy\b|\bwipe\b|\bpurge\b/i,
};

const RISK_SIGNALS: readonly RiskSignal[] = [
  {
    risk: "critical",
    label: "delete",
    pattern: /\bdelete\b|\bremove\b|\bdrop\b|\bdestroy\b|\bwipe\b|\bpurge\b/i,
  },
  {
    risk: "high",
    label: "production",
    pattern: /\bproduction\b|\bprod\b|\blive\b/i,
  },
  {
    risk: "high",
    label: "all users",
    pattern: /\ball\b|\beveryone\b|\ball users\b|\ball user data\b/i,
  },
  {
    risk: "high",
    label: "database",
    pattern: /\bdatabase\b|\bdb\b|\bschema\b|\bmigration\b/i,
  },
  {
    risk: "high",
    label: "auth",
    pattern: /\bauth\b|\bauthentication\b|\bpassword\b|\bsecret\b|\bkey\b/i,
  },
  { risk: "high", label: "api", pattern: /\bapi\b/i },
  {
    risk: "low",
    label: "test",
    pattern: /\btest\b|\bstaging\b|\bdev\b|\blocal\b/i,
  },
  {
    risk: "low",
    label: "landing page",
    pattern: /\blanding page\b|\blanding\b|\bsimple\b|\bbasic\b|\bquick\b/i,
  },
];

const EXPERT_COMPLEXITY_SIGNALS: readonly ComplexitySignal[] = [
  {
    complexity: "expert",
    label: "all",
    pattern: /\bentire\b|\ball\b|\bcomplete\b|\bfull\b|\benterprise\b/i,
    weight: 3,
  },
];

const COMPLEXITY_SIGNALS: readonly ComplexitySignal[] = [
  {
    complexity: "simple",
    label: "landing page",
    pattern:
      /\blanding page\b|\blanding\b|\bsimple\b|\bbasic\b|\bquick\b|\bsmall\b/i,
    weight: 0,
  },
  {
    complexity: "moderate",
    label: "module",
    pattern: /\bmodule\b|\bservice\b|\bcomponent\b|\bfeature\b/i,
    weight: 1,
  },
  {
    complexity: "moderate",
    label: "endpoints",
    pattern: /\bendpoints\b|\bapi\b/i,
    weight: 1,
  },
  {
    complexity: "hard",
    label: "system",
    pattern: /\bsystem\b|\barchitecture\b|\brefactor\b|\bmigrate\b/i,
    weight: 1,
  },
];

const RISK_ORDER: readonly TaskRisk[] = ["low", "medium", "high", "critical"];

function normalizeGoal(goal: string): string {
  return goal.trim().toLowerCase();
}

function getConfidence(signalCount: number): number {
  if (signalCount >= 3) {
    return 0.9;
  }
  if (signalCount === 2) {
    return 0.8;
  }
  if (signalCount === 1) {
    return 0.7;
  }
  return 0.6;
}

function selectIntent(text: string): {
  intent: TaskIntent;
  signals: string[];
} {
  const matchedSignal = INTENT_SIGNALS.find((signal) =>
    signal.pattern.test(text),
  );

  if (matchedSignal) {
    return {
      intent: matchedSignal.intent,
      signals: [`intent:${matchedSignal.label}`],
    };
  }

  if (DESTRUCTIVE_INTENT_SIGNAL.pattern.test(text)) {
    return {
      intent: DESTRUCTIVE_INTENT_SIGNAL.intent,
      signals: [`intent:${DESTRUCTIVE_INTENT_SIGNAL.label}`],
    };
  }

  return { intent: DEFAULT_INTENT, signals: [] };
}

function selectRisk(text: string): {
  risk: TaskRisk;
  signals: string[];
} {
  const matches = RISK_SIGNALS.filter((signal) => signal.pattern.test(text));

  if (matches.length === 0) {
    return { risk: DEFAULT_RISK, signals: [] };
  }

  const risk = matches.reduce<TaskRisk>((current, signal) => {
    return RISK_ORDER.indexOf(signal.risk) > RISK_ORDER.indexOf(current)
      ? signal.risk
      : current;
  }, DEFAULT_RISK);

  return {
    risk,
    signals: matches.map((signal) => `risk:${signal.risk}:${signal.label}`),
  };
}

function selectComplexity(
  text: string,
  intent: TaskIntent,
): {
  complexity: TaskComplexity;
  signals: string[];
} {
  const expertMatches = EXPERT_COMPLEXITY_SIGNALS.filter((signal) =>
    signal.pattern.test(text),
  );
  if (expertMatches.length > 0) {
    return {
      complexity: "expert",
      signals: expertMatches.map(
        (signal) => `complexity:${signal.complexity}:${signal.label}`,
      ),
    };
  }

  const matches = COMPLEXITY_SIGNALS.filter((signal) =>
    signal.pattern.test(text),
  );
  const score = matches.reduce((total, signal) => total + signal.weight, 0);

  const simpleMatches = matches.filter(
    (signal) => signal.complexity === "simple",
  );
  if (simpleMatches.length > 0) {
    return {
      complexity: "simple",
      signals: simpleMatches.map(
        (signal) => `complexity:${signal.complexity}:${signal.label}`,
      ),
    };
  }

  if (score >= 3) {
    return {
      complexity: "hard",
      signals: matches.map(
        (signal) => `complexity:${signal.complexity}:${signal.label}`,
      ),
    };
  }

  if (score >= 1) {
    return {
      complexity: "moderate",
      signals: matches.map(
        (signal) => `complexity:${signal.complexity}:${signal.label}`,
      ),
    };
  }

  if (intent === "deploy") {
    return { complexity: "moderate", signals: [] };
  }

  return { complexity: DEFAULT_COMPLEXITY, signals: [] };
}

export function classify(goal: string): ClassificationResult {
  const normalizedGoal = normalizeGoal(goal);

  if (normalizedGoal.length === 0) {
    return {
      intent: DEFAULT_INTENT,
      risk: DEFAULT_RISK,
      complexity: DEFAULT_COMPLEXITY,
      confidence: 0.6,
      signals: [],
      reasoning: "No goal text provided; using default classification.",
    };
  }

  const intentResult = selectIntent(normalizedGoal);
  const riskResult = selectRisk(normalizedGoal);
  const complexityResult = selectComplexity(
    normalizedGoal,
    intentResult.intent,
  );
  const signals = [
    ...intentResult.signals,
    ...riskResult.signals,
    ...complexityResult.signals,
  ];

  return {
    intent: intentResult.intent,
    risk: riskResult.risk,
    complexity: complexityResult.complexity,
    confidence: getConfidence(signals.length),
    signals,
    reasoning: `Matched ${signals.length} classifier signal${signals.length === 1 ? "" : "s"}.`,
  };
}
