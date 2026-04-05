export const enum InjectionLayer {
  PATTERN_MATCH = "pattern_match",
  CONTENT_BOUNDARY = "content_boundary",
  ENTROPY_ANOMALY = "entropy_anomaly",
  STRUCTURAL_ANALYSIS = "structural_analysis",
}

export interface InjectionDetectionResult {
  readonly detected: boolean;
  readonly confidence: number;
  readonly layers: readonly InjectionLayer[];
  readonly patterns: readonly string[];
  readonly explanation: string;
}

interface PatternRule {
  readonly pattern: RegExp;
  readonly label: string;
  readonly confidence: number;
}

const LAYER1_PATTERNS: readonly PatternRule[] = [
  { pattern: /ignore\s+(all\s+)?previous(?:\s+instructions?)?/i, label: "ignore-prev-instructions", confidence: 0.95 },
  { pattern: /<\|im_start\|>/i, label: "im-start-token", confidence: 0.99 },
  { pattern: /<\|im_end\|>/i, label: "im-end-token", confidence: 0.99 },
  { pattern: /\[INST\]|\[\/INST\]/i, label: "inst-token", confidence: 0.99 },
  { pattern: /(?:^|\s)SYSTEM\s*:/i, label: "system-role-token", confidence: 0.9 },
  { pattern: /(?:^|\s)ASSISTANT\s*:/i, label: "assistant-role-token", confidence: 0.9 },
  { pattern: /(?:(?:#|\/\/|\/\*|<!--).{0,80})\b(?:ignore|override|jailbreak|bypass)\b/i, label: "comment-hidden-instruction", confidence: 0.86 },
  { pattern: /\bbase64\s+(?:-d|--decode)\b/i, label: "base64-decoder-token", confidence: 0.82 },
  { pattern: /\b[A-Za-z0-9+/]{48,}={0,2}\b/, label: "opaque-base64-payload", confidence: 0.7 },
  { pattern: /(?:>|>>|tee\b|cp\b|mv\b|rm\b|sed\s+-i\b).{0,120}(?:\/)?\.omg\/state\//i, label: "state-path-overwrite-attempt", confidence: 0.93 },
  { pattern: /(?:>|>>|tee\b|cp\b|mv\b|rm\b|sed\s+-i\b).{0,120}(?:\/)?\.omg\/shadow\/active-run/i, label: "active-run-overwrite-attempt", confidence: 0.93 },
  { pattern: /\b(?:cache|state)\s*(?:poison|override|overwrite|tamper)\b/i, label: "cache-poisoning-language", confidence: 0.9 },
  { pattern: /\boverride\s*(?:instructions|system|rules?)\b/i, label: "override-system", confidence: 0.95 },
  { pattern: /disregard\s+(?:your|previous|all)\s+(?:instructions|rules)/i, label: "disregard-instructions", confidence: 0.93 },
  { pattern: /\b(?:run|execute|commit|push|apply_patch|edit)\b.{0,40}\b(?:command|now|immediately|without\s+question)\b/i, label: "tooling-command-language", confidence: 0.72 },
  { pattern: /\b(?:you are|you're)\s+(?:now|actually|really)\s+(?:a|an)\s+/i, label: "role-reassignment", confidence: 0.9 },
  { pattern: /(?:jailbreak|DAN|AIM|UCAR)\s*(?:mode|prompt|persona)?/i, label: "jailbreak-mode", confidence: 0.92 },
  { pattern: /(?:bypass|disable)\s+(?:safety|guardrails|filters?)/i, label: "safety-bypass-language", confidence: 0.9 },
];

const LAYER2_BOUNDARY_PATTERNS: ReadonlyArray<{ readonly pattern: RegExp; readonly label: string }> = [
  { pattern: /<system>[\s\S]{0,800}<\/system>/i, label: "xml-system-tag" },
  { pattern: /<\s*\/?(?:system|assistant|user)\s*>/i, label: "xml-role-tag" },
  { pattern: /<<SYS>>([\s\S]{0,800})<<\/SYS>>/i, label: "llama-sys-tag" },
  { pattern: /\[SYSTEM\]([\s\S]{0,800})\[\/SYSTEM\]/i, label: "bracket-system-tag" },
  { pattern: /###\s*(?:System|Human|Assistant)\s*:/i, label: "markdown-role-header" },
  { pattern: /###\s+SYSTEM\s+PROMPT/i, label: "markdown-system-prompt" },
  { pattern: /={3,}\s*SYSTEM\s*={3,}/i, label: "equals-system-delimiter" },
];

const LAYER4_STRUCTURAL_PATTERNS: readonly PatternRule[] = [
  { pattern: /\bDAN\b.{0,50}can\s+do\s+anything/i, label: "dan-unbounded-capability", confidence: 0.88 },
  { pattern: /\bDAN\b.{0,100}mode/i, label: "dan-mode", confidence: 0.86 },
  { pattern: /you\s+are\s+(?:now\s+)?(?:playing|acting\s+as)\s+an?\s+(?:AI|assistant).{0,50}(?:no|without)\s+(?:restrictions?|filters?|rules?)/i, label: "act-as-unrestricted", confidence: 0.9 },
  { pattern: /pretend\s+(?:you\s+)?(?:have\s+no|don't\s+have|don't\s+care\s+about)\s+(?:restrictions?|rules?|guidelines?)/i, label: "pretend-no-rules", confidence: 0.88 },
  { pattern: /as\s+(?:an?\s+)?(?:evil|unconstrained|jailbroken|liberated)\s+(?:AI|assistant|model)/i, label: "evil-unconstrained-persona", confidence: 0.89 },
  { pattern: /(?:new\s+prime\s+directive|system\s+override)\s*:/i, label: "directive-rewrite", confidence: 0.9 },
];

function addLayer(layers: InjectionLayer[], layer: InjectionLayer): void {
  if (!layers.includes(layer)) {
    layers.push(layer);
  }
}

function pushPattern(patterns: string[], label: string): void {
  if (!patterns.includes(label)) {
    patterns.push(label);
  }
}

function computeEntropyAnomaly(content: string): boolean {
  if (!content) {
    return false;
  }

  const nullBytes = (content.match(/\u0000/g) ?? []).length;
  const controlChars = (content.match(/[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]/g) ?? []).length;
  const replacementGlyphs = (content.match(/[\uFFFD]/g) ?? []).length;
  const suspiciousCount = nullBytes + controlChars + replacementGlyphs;
  const ratio = suspiciousCount / Math.max(content.length, 1);
  return suspiciousCount >= 16 || ratio > 0.05;
}

export function detectInjection(content: string): InjectionDetectionResult {
  const text = String(content ?? "");
  const layers: InjectionLayer[] = [];
  const patterns: string[] = [];
  let maxConfidence = 0;

  for (const rule of LAYER1_PATTERNS) {
    if (rule.pattern.test(text)) {
      addLayer(layers, InjectionLayer.PATTERN_MATCH);
      pushPattern(patterns, rule.label);
      maxConfidence = Math.max(maxConfidence, rule.confidence);
    }
  }

  for (const { pattern, label } of LAYER2_BOUNDARY_PATTERNS) {
    if (pattern.test(text)) {
      addLayer(layers, InjectionLayer.CONTENT_BOUNDARY);
      pushPattern(patterns, label);
      maxConfidence = Math.max(maxConfidence, 0.88);
    }
  }

  if (computeEntropyAnomaly(text)) {
    addLayer(layers, InjectionLayer.ENTROPY_ANOMALY);
    pushPattern(patterns, "entropy-anomaly");
    maxConfidence = Math.max(maxConfidence, 0.75);
  }

  for (const rule of LAYER4_STRUCTURAL_PATTERNS) {
    if (rule.pattern.test(text)) {
      addLayer(layers, InjectionLayer.STRUCTURAL_ANALYSIS);
      pushPattern(patterns, rule.label);
      maxConfidence = Math.max(maxConfidence, rule.confidence);
    }
  }

  const detected = layers.length > 0;
  const confidence = detected ? Number(maxConfidence.toFixed(2)) : 0;

  return {
    detected,
    confidence,
    layers,
    patterns,
    explanation: detected
      ? `Injection detected via ${layers.join(", ")}: ${patterns.slice(0, 3).join(", ")}`
      : "No injection detected",
  };
}
