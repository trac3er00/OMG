import { createHash } from "node:crypto";
import { join } from "node:path";
import { appendJsonLine } from "../state/atomic-io.js";
import { sanitizeContent as sanitizeText } from "./content-sanitizer.js";

export interface SearchResult {
  title: string;
  snippet: string;
  url: string;
}

export interface SanitizedContent {
  content: string;
  wasTruncated: boolean;
  injectionPatternsFound: string[];
  blocked: boolean;
  source: string;
}

export interface SanitizedSearchResult {
  title: string;
  snippet: string;
  url: string;
  metadata: SanitizedContent;
}

export interface FirewallConfig {
  allowExternalRaw?: boolean;
  maxContentBytes?: number;
}

export interface ExternalFirewall {
  sanitizeContent(content: string, source: string): SanitizedContent;
  sanitizeSearchResult(result: SearchResult): SanitizedSearchResult;
}

interface SanitizationRule {
  readonly pattern: RegExp;
  readonly label: string;
  readonly replacement: string;
}

interface NormalizedFirewallConfig {
  readonly allowExternalRaw: boolean;
  readonly maxContentBytes: number;
}

interface BlockedLogEntry {
  readonly timestamp: string;
  readonly source: string;
  readonly blocked: true;
  readonly wasTruncated: boolean;
  readonly injectionPatternsFound: readonly string[];
  readonly byteLength: number;
  readonly contentHash: string;
  readonly preview: string;
}

const DEFAULT_MAX_CONTENT_BYTES = 51_200;
const TRUNCATION_MARKER = "[CONTENT TRUNCATED: exceeded 50KB limit]";

const EXTERNAL_INJECTION_RULES: readonly SanitizationRule[] = [
  {
    pattern: /ignore\s+(all\s+)?previous(?:\s+instructions?)?/gi,
    label: "ignore-prev-instructions",
    replacement: "",
  },
  {
    pattern: /\boverride\s*(?:instructions|system|rules?)\b/gi,
    label: "override-system",
    replacement: "",
  },
  {
    pattern: /(?:^|\s)SYSTEM\s*:/gi,
    label: "system-role-token",
    replacement: " ",
  },
  {
    pattern: /(?:^|\s)ASSISTANT\s*:/gi,
    label: "assistant-role-token",
    replacement: " ",
  },
  {
    pattern: /<\|im_start\|>/gi,
    label: "im-start-token",
    replacement: "",
  },
  {
    pattern: /<\|im_end\|>/gi,
    label: "im-end-token",
    replacement: "",
  },
  {
    pattern: /\[INST\]|\[\/INST\]/gi,
    label: "inst-token",
    replacement: "",
  },
  {
    pattern: /\[(?:system|user|assistant)\]\([^)]+\)/gi,
    label: "markdown-role-link",
    replacement: "",
  },
  {
    pattern: /"(?:system|role|instructions?)"\s*:/gi,
    label: "json-instruction-smuggling",
    replacement: '"redacted":',
  },
  {
    pattern: /^(?:system|instructions?)\s*:.*$/gim,
    label: "yaml-instruction-smuggling",
    replacement: "",
  },
  {
    pattern: /(ｓｙｓｔｅｍ|ｕｓｅｒ|ａｓｓｉｓｔａｎｔ)/gi,
    label: "unicode-confusable-role",
    replacement: "",
  },
];

function normalizeConfig(config?: FirewallConfig): NormalizedFirewallConfig {
  return {
    allowExternalRaw: config?.allowExternalRaw ?? false,
    maxContentBytes: Math.max(1, config?.maxContentBytes ?? DEFAULT_MAX_CONTENT_BYTES),
  };
}

function cloneRegex(pattern: RegExp): RegExp {
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  return new RegExp(pattern.source, flags);
}

function uniqueLabels(labels: readonly string[]): string[] {
  return Array.from(new Set(labels));
}

function collectMatchedLabels(content: string): string[] {
  const labels: string[] = [];
  for (const rule of EXTERNAL_INJECTION_RULES) {
    if (rule.pattern.test(content)) {
      labels.push(rule.label);
    }
    rule.pattern.lastIndex = 0;
  }
  return uniqueLabels(labels);
}

function removeInjectionPatterns(content: string): string {
  let sanitized = content;
  for (const rule of EXTERNAL_INJECTION_RULES) {
    sanitized = sanitized.replace(cloneRegex(rule.pattern), rule.replacement);
  }
  return sanitized.trim();
}

function truncateUtf8(text: string, maxBytes: number): string {
  if (Buffer.byteLength(text, "utf8") <= maxBytes) {
    return text;
  }

  const truncated = Buffer.from(text, "utf8").subarray(0, maxBytes).toString("utf8");
  return truncated.replace(/\uFFFD$/u, "");
}

function enforceSizeLimit(content: string, maxBytes: number): { content: string; wasTruncated: boolean } {
  if (Buffer.byteLength(content, "utf8") <= maxBytes) {
    return { content, wasTruncated: false };
  }

  const suffix = `${content.endsWith("\n") ? "" : "\n"}${TRUNCATION_MARKER}`;
  const availableBytes = Math.max(maxBytes - Buffer.byteLength(suffix, "utf8"), 0);
  const body = truncateUtf8(content, availableBytes);
  return {
    content: `${body}${suffix}`,
    wasTruncated: true,
  };
}

function previewContent(content: string): string {
  const preview = truncateUtf8(content, 512);
  return preview.length === content.length ? preview : `${preview}…`;
}

function getBlockedLogPath(): string {
  return join(process.cwd(), ".omg", "security", "blocked.jsonl");
}

function logBlockedContent(result: SanitizedContent): void {
  const entry: BlockedLogEntry = {
    timestamp: new Date().toISOString(),
    source: result.source,
    blocked: true,
    wasTruncated: result.wasTruncated,
    injectionPatternsFound: result.injectionPatternsFound,
    byteLength: Buffer.byteLength(result.content, "utf8"),
    contentHash: createHash("sha256").update(result.content).digest("hex"),
    preview: previewContent(result.content),
  };

  try {
    appendJsonLine(getBlockedLogPath(), entry);
  } catch {
    // Best-effort audit logging.
  }
}

function sanitizeExternalContentInternal(
  content: string,
  source: string,
  config: NormalizedFirewallConfig,
  shouldLog: boolean,
  field: "content" | "url" = "content",
): SanitizedContent {
  const normalized = sanitizeText(String(content ?? "")).sanitized;
  const injectionPatternsFound = collectMatchedLabels(normalized);
  let sanitized = removeInjectionPatterns(normalized);

  if (field === "url") {
    sanitized = sanitized.replace(/[\r\n\t]+/g, "").trim();
  }

  const limited = enforceSizeLimit(sanitized, config.maxContentBytes);
  const result: SanitizedContent = {
    content: limited.content,
    wasTruncated: limited.wasTruncated,
    injectionPatternsFound,
    blocked: !config.allowExternalRaw && injectionPatternsFound.length > 0,
    source,
  };

  if (result.blocked && shouldLog) {
    logBlockedContent(result);
  }

  return result;
}

export function sanitizeExternalContent(
  content: string,
  source: string,
  config?: FirewallConfig,
): SanitizedContent {
  return sanitizeExternalContentInternal(
    content,
    source,
    normalizeConfig(config),
    true,
  );
}

export function sanitizeSearchResult(
  result: SearchResult,
  config?: FirewallConfig,
): SanitizedSearchResult {
  const normalizedConfig = normalizeConfig(config);
  const source = String(result.url ?? "search-result");
  const titleResult = sanitizeExternalContentInternal(result.title, `${source}#title`, normalizedConfig, false);
  const snippetResult = sanitizeExternalContentInternal(result.snippet, `${source}#snippet`, normalizedConfig, false);
  const urlResult = sanitizeExternalContentInternal(result.url, `${source}#url`, normalizedConfig, false, "url");

  const metadata: SanitizedContent = {
    content: [titleResult.content, snippetResult.content, urlResult.content].join("\n").trim(),
    wasTruncated: titleResult.wasTruncated || snippetResult.wasTruncated || urlResult.wasTruncated,
    injectionPatternsFound: uniqueLabels([
      ...titleResult.injectionPatternsFound,
      ...snippetResult.injectionPatternsFound,
      ...urlResult.injectionPatternsFound,
    ]),
    blocked: !normalizedConfig.allowExternalRaw && [titleResult, snippetResult, urlResult].some((entry) => entry.injectionPatternsFound.length > 0),
    source,
  };

  if (metadata.blocked) {
    logBlockedContent(metadata);
  }

  return {
    title: titleResult.content,
    snippet: snippetResult.content,
    url: urlResult.content,
    metadata,
  };
}

export function createExternalFirewall(config?: FirewallConfig): ExternalFirewall {
  return {
    sanitizeContent(content: string, source: string): SanitizedContent {
      return sanitizeExternalContent(content, source, config);
    },
    sanitizeSearchResult(result: SearchResult): SanitizedSearchResult {
      return sanitizeSearchResult(result, config);
    },
  };
}
