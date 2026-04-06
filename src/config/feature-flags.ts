/**
 * Feature flag resolution with 4-level precedence:
 *   1. Environment variables (OMG_FEATURE_* = "1"/"true"/"0"/"false")
 *   2. Runtime overrides (in-memory, programmatic)
 *   3. settings.json _omg.features
 *   4. Preset defaults
 *
 * Mirrors hooks/_common.py:get_feature_flag()
 */

import type { FeatureFlags, PresetName } from "../types/config.js";
import { getPresetFeatures } from "./presets.js";

const OMG_ENV_PREFIX = "OMG_FEATURE_";

/** Convert a feature flag name to an env var name */
function toEnvVar(flagName: string): string {
  return OMG_ENV_PREFIX + flagName.toUpperCase().replace(/-/g, "_");
}

/** Parse an env var value as boolean */
function parseEnvBool(value: string): boolean | undefined {
  if (value === "1" || value.toLowerCase() === "true") return true;
  if (value === "0" || value.toLowerCase() === "false") return false;
  return undefined;
}

export class FeatureFlagResolver {
  private readonly presetFeatures: FeatureFlags;
  private readonly settingsFeatures: FeatureFlags;
  private readonly overrides: Map<string, boolean> = new Map();

  constructor(preset: PresetName, settingsFeatures?: FeatureFlags) {
    this.presetFeatures = getPresetFeatures(preset);
    this.settingsFeatures = settingsFeatures ?? {};
  }

  /**
   * Resolve a feature flag following precedence rules:
   * env var > override > settings > preset > defaultValue
   */
  resolve(flagName: string, defaultValue = false): boolean {
    // 1. Environment variable (highest priority)
    const envVal = process.env[toEnvVar(flagName)];
    if (envVal !== undefined) {
      const parsed = parseEnvBool(envVal);
      if (parsed !== undefined) return parsed;
    }

    // 2. Runtime override
    if (this.overrides.has(flagName)) {
      return this.overrides.get(flagName)!;
    }

    // 3. settings.json _omg.features
    if (flagName in this.settingsFeatures) {
      const val = this.settingsFeatures[flagName];
      if (val !== undefined) return val;
    }

    // 4. Preset default
    if (flagName in this.presetFeatures) {
      const val = this.presetFeatures[flagName];
      if (val !== undefined) return val;
    }

    return defaultValue;
  }

  /** Set a runtime override (useful for testing) */
  override(flagName: string, value: boolean): void {
    this.overrides.set(flagName, value);
  }

  /** Clear all runtime overrides */
  clearOverrides(): void {
    this.overrides.clear();
  }

  /** Get all resolved flags */
  resolveAll(): FeatureFlags {
    const allFlags = new Set([
      ...Object.keys(this.presetFeatures),
      ...Object.keys(this.settingsFeatures),
      ...this.overrides.keys(),
    ]);

    const result: FeatureFlags = {};
    for (const flag of allFlags) {
      result[flag] = this.resolve(flag);
    }
    return result;
  }
}

/** Singleton-like cache for the current resolver */
let _currentResolver: FeatureFlagResolver | null = null;

export function getFeatureFlagResolver(): FeatureFlagResolver {
  if (!_currentResolver) {
    _currentResolver = new FeatureFlagResolver("standard");
  }
  return _currentResolver;
}

export function setFeatureFlagResolver(resolver: FeatureFlagResolver): void {
  _currentResolver = resolver;
}

/** Convenience: get a single feature flag using the current resolver */
export function getFeatureFlag(
  flagName: string,
  defaultValue = false,
): boolean {
  return getFeatureFlagResolver().resolve(flagName, defaultValue);
}
