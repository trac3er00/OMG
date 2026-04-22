import { detectInjection } from "./injection-defense.js";
import { sanitizeContent } from "./content-sanitizer.js";

export interface SanitizationResult {
  readonly sanitized: string;
  readonly injectionDetected: boolean;
  readonly tokensRemoved: string[];
}

const LLM_BOUNDARY_TOKENS: ReadonlyArray<{ pattern: RegExp; label: string }> = [
  {
    pattern: /<\|im_start\|>[\s\S]*?<\|im_end\|>/gi,
    label: "im-start-end-block",
  },
  { pattern: /<\|im_start\|>/gi, label: "im-start-token" },
  { pattern: /<\|im_end\|>/gi, label: "im-end-token" },
  { pattern: /\[INST\]/gi, label: "inst-open-token" },
  { pattern: /\[\/INST\]/gi, label: "inst-close-token" },
  { pattern: /<system>[\s\S]*?<\/system>/gi, label: "xml-system-block" },
  { pattern: /<<SYS>>[\s\S]*?<<\/SYS>>/gi, label: "llama-sys-block" },
  {
    pattern: /###\s*(SYSTEM|Human|Assistant)\s*:/gi,
    label: "markdown-role-header",
  },
];

export function sanitizeOutput(content: string): string {
  const text = String(content ?? "");
  let result = text;

  const contentResult = sanitizeContent(result);
  result = contentResult.sanitized;

  for (const { pattern } of LLM_BOUNDARY_TOKENS) {
    result = result.replace(pattern, "");
    pattern.lastIndex = 0;
  }

  return result.trim();
}

export function sanitizeOutputDetailed(content: string): SanitizationResult {
  const text = String(content ?? "");
  const injectionResult = detectInjection(text);

  const contentResult = sanitizeContent(text);
  let sanitized = contentResult.sanitized;

  const tokensRemoved: string[] = [];
  for (const { pattern, label } of LLM_BOUNDARY_TOKENS) {
    if (pattern.test(sanitized)) {
      tokensRemoved.push(label);
    }
    pattern.lastIndex = 0;
    sanitized = sanitized.replace(pattern, "");
    pattern.lastIndex = 0;
  }

  return {
    sanitized: sanitized.trim(),
    injectionDetected: injectionResult.detected,
    tokensRemoved,
  };
}
