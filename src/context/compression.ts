import {
  type ContextState,
  computePressure,
  type StrategyName,
} from "./strategy-router.js";

export type CompressionLevel = 1 | 2 | 3;

export interface CompressionResult {
  readonly level: CompressionLevel;
  readonly original_tokens: number;
  readonly compressed_tokens: number;
  readonly retention_rate: number;
  readonly strategy_used: StrategyName;
}

export interface CompressionOptions {
  readonly reconstructionBoundary?: boolean;
}

export interface PressureResponse {
  readonly pressure: number;
  readonly level: "advisory" | "automatic" | "emergency";
  readonly action: "suggest" | "compress" | "reconstruct";
  readonly threshold: number;
}

export const ADVISORY_THRESHOLD = 0.5;
export const AUTOMATIC_THRESHOLD = 0.7;
export const EMERGENCY_THRESHOLD = 0.85;

export function classifyPressureLevel(pressure: number): PressureResponse {
  if (pressure >= EMERGENCY_THRESHOLD) {
    return {
      pressure,
      level: "emergency",
      action: "reconstruct",
      threshold: EMERGENCY_THRESHOLD,
    };
  }
  if (pressure >= AUTOMATIC_THRESHOLD) {
    return {
      pressure,
      level: "automatic",
      action: "compress",
      threshold: AUTOMATIC_THRESHOLD,
    };
  }
  if (pressure >= ADVISORY_THRESHOLD) {
    return {
      pressure,
      level: "advisory",
      action: "suggest",
      threshold: ADVISORY_THRESHOLD,
    };
  }
  return {
    pressure,
    level: "advisory",
    action: "suggest",
    threshold: ADVISORY_THRESHOLD,
  };
}

export function applyLevel1Compression(tokens: number): CompressionResult {
  const compressed = Math.floor(tokens * 0.85);
  return {
    level: 1,
    original_tokens: tokens,
    compressed_tokens: compressed,
    retention_rate: 0.95,
    strategy_used: "keep-last-n",
  };
}

export function applyLevel2Compression(tokens: number): CompressionResult {
  const compressed = Math.floor(tokens * 0.55);
  return {
    level: 2,
    original_tokens: tokens,
    compressed_tokens: compressed,
    retention_rate: 0.82,
    strategy_used: "summarize",
  };
}

export function applyLevel3Compression(tokens: number): CompressionResult {
  const compressed = Math.floor(tokens * 0.2);
  return {
    level: 3,
    original_tokens: tokens,
    compressed_tokens: compressed,
    retention_rate: 0.6,
    strategy_used: "discard-all",
  };
}

export function selectCompressionLevel(pressure: number): CompressionLevel {
  if (pressure >= EMERGENCY_THRESHOLD) return 3;
  if (pressure >= AUTOMATIC_THRESHOLD) return 2;
  return 1;
}

export function compress(
  state: ContextState,
  options: CompressionOptions = {},
): CompressionResult {
  if (options.reconstructionBoundary === true) {
    return {
      level: 1,
      original_tokens: state.totalTokens,
      compressed_tokens: state.totalTokens,
      retention_rate: 1,
      strategy_used: "durability",
    };
  }

  const pressure = computePressure(state);
  const level = selectCompressionLevel(pressure);
  switch (level) {
    case 3:
      return applyLevel3Compression(state.totalTokens);
    case 2:
      return applyLevel2Compression(state.totalTokens);
    default:
      return applyLevel1Compression(state.totalTokens);
  }
}
