import type { ContextLimitEntry } from "../types/runtime.js";

const CONTEXT_LIMITS: Record<string, ContextLimitEntry> = {
  "claude-opus-4-6": {
    context_tokens: 1_000_000,
    output_reserve_tokens: 128_000,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 150_000,
    notes: "Claude Opus 4.6 native 1M context window",
  },
  "claude-sonnet-4-6": {
    context_tokens: 1_000_000,
    output_reserve_tokens: 64_000,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 150_000,
    notes: "Claude Sonnet 4.6 native 1M context window",
  },
  "claude-haiku-4-5": {
    context_tokens: 200_000,
    output_reserve_tokens: 64_000,
    class_label: "200k-class",
    preflight_counting: true,
    native_compaction: false,
    compaction_trigger_default: 120_000,
    notes: "Claude Haiku 4.5 has a 200k context window",
  },
  "claude-sonnet-4-5": {
    context_tokens: 200_000,
    output_reserve_tokens: 64_000,
    class_label: "200k-class",
    preflight_counting: true,
    native_compaction: false,
    compaction_trigger_default: 120_000,
    notes: "Claude Sonnet 4.5 defaults to 200k",
  },
  "gpt-5.4": {
    context_tokens: 1_050_000,
    output_reserve_tokens: 128_000,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 200_000,
    notes: "GPT-5.4 supports 1,050,000 context tokens",
  },
  "gpt-5": {
    context_tokens: 400_000,
    output_reserve_tokens: 128_000,
    class_label: "400k-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 250_000,
    notes: "GPT-5 family baseline",
  },
  "gpt-4.1": {
    context_tokens: 1_047_576,
    output_reserve_tokens: 32_768,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 200_000,
    notes: "GPT-4.1 has 1,047,576 context tokens",
  },
  "gpt-4o": {
    context_tokens: 128_000,
    output_reserve_tokens: 16_384,
    class_label: "128k-class",
    preflight_counting: true,
    native_compaction: true,
    compaction_trigger_default: 80_000,
    notes: "GPT-4o legacy context window",
  },
  "gemini-3.1-pro-preview": {
    context_tokens: 1_048_576,
    output_reserve_tokens: 65_536,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: false,
    compaction_trigger_default: 150_000,
    notes: "Gemini 3.1 Pro Preview",
  },
  "gemini-2.5-pro": {
    context_tokens: 1_048_576,
    output_reserve_tokens: 65_536,
    class_label: "1M-class",
    preflight_counting: true,
    native_compaction: false,
    compaction_trigger_default: 150_000,
    notes: "Gemini 2.5 Pro",
  },
  "gemini-3-flash": {
    context_tokens: 200_000,
    output_reserve_tokens: 32_768,
    class_label: "200k-class",
    preflight_counting: true,
    native_compaction: false,
    compaction_trigger_default: 120_000,
    notes: "Gemini 3 Flash",
  },
  "kimi-k2.5": {
    context_tokens: 256_000,
    output_reserve_tokens: 32_768,
    class_label: "256k-class",
    preflight_counting: false,
    native_compaction: false,
    compaction_trigger_default: 160_000,
    notes: "Kimi K2.5 baseline",
  },
};

const PREFIX_TABLE: ReadonlyArray<readonly [string, string]> = [
  ["claude-opus-4-6", "claude-opus-4-6"],
  ["claude-sonnet-4-6", "claude-sonnet-4-6"],
  ["claude-haiku-4-5", "claude-haiku-4-5"],
  ["claude-sonnet-4-5", "claude-sonnet-4-5"],
  ["claude-sonnet-4", "claude-sonnet-4-5"],
  ["claude-opus-4", "claude-haiku-4-5"],
  ["claude-3-5-sonnet", "claude-sonnet-4-5"],
  ["claude-", "claude-haiku-4-5"],
  ["gpt-5.4", "gpt-5.4"],
  ["gpt-5", "gpt-5"],
  ["gpt-4.1", "gpt-4.1"],
  ["gpt-4", "gpt-4o"],
  ["gpt-4o", "gpt-4o"],
  ["gemini-3.1", "gemini-3.1-pro-preview"],
  ["gemini-3", "gemini-3-flash"],
  ["gemini-2.5", "gemini-2.5-pro"],
  ["gemini-1.5", "gemini-2.5-pro"],
  ["gemini-", "gemini-3-flash"],
  ["kimi-k2", "kimi-k2.5"],
  ["kimi-", "kimi-k2.5"],
  ["moonshot-v1", "kimi-k2.5"],
];

const DEFAULT_LIMIT: ContextLimitEntry = {
  context_tokens: 128_000,
  output_reserve_tokens: 8_192,
  class_label: "128k-class",
  preflight_counting: false,
  native_compaction: false,
  compaction_trigger_default: 80_000,
  notes: "Unknown model fallback",
};

function cloneLimit(limit: ContextLimitEntry): ContextLimitEntry {
  return {
    context_tokens: limit.context_tokens,
    output_reserve_tokens: limit.output_reserve_tokens,
    class_label: limit.class_label,
    preflight_counting: limit.preflight_counting,
    native_compaction: limit.native_compaction,
    compaction_trigger_default: limit.compaction_trigger_default,
    notes: limit.notes,
  };
}

export function getContextLimit(model: string): ContextLimitEntry {
  const normalized = model.trim().toLowerCase();
  if (normalized.length === 0) {
    return cloneLimit(DEFAULT_LIMIT);
  }

  const exact = CONTEXT_LIMITS[normalized];
  if (exact) {
    return cloneLimit(exact);
  }

  for (const [prefix, key] of PREFIX_TABLE) {
    if (normalized.startsWith(prefix)) {
      return cloneLimit(CONTEXT_LIMITS[key]!);
    }
  }

  return cloneLimit(DEFAULT_LIMIT);
}

export function getAllContextLimits(): Readonly<Record<string, ContextLimitEntry>> {
  return CONTEXT_LIMITS;
}
