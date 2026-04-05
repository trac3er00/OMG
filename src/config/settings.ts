/**
 * Settings loader for OMG v3.
 *
 * Loads settings.json, validates with Zod, merges env var overrides.
 * Provides the full resolved configuration for the current session.
 */

import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { SettingsSchema, type Settings, type PresetName } from "../types/config.js";
import { FeatureFlagResolver } from "./feature-flags.js";

export interface ResolvedSettings {
  readonly raw: Settings;
  readonly preset: PresetName;
  readonly featureFlags: FeatureFlagResolver;
  readonly projectDir: string;
  readonly settingsPath: string;
}

/**
 * Load and validate settings.json from the project directory.
 * Merges env var overrides and creates feature flag resolver.
 *
 * @example
 * const settings = loadSettings("/path/to/project");
 * const isMutationGateEnabled = settings.featureFlags.resolve("mutation-gate");
 */
export function loadSettings(projectDir?: string): ResolvedSettings {
  const dir = resolve(projectDir ?? process.cwd());
  const settingsPath = join(dir, "settings.json");

  let raw: Settings = {};

  if (existsSync(settingsPath)) {
    try {
      const content = readFileSync(settingsPath, "utf8");
      const parsed = JSON.parse(content) as unknown;
      const result = SettingsSchema.safeParse(parsed);
      if (result.success) {
        raw = result.data;
      } else {
        // Invalid settings — use defaults, don't crash
        console.warn(`[OMG] settings.json parse error: ${result.error.message}`);
      }
    } catch (err) {
      console.warn(`[OMG] Could not read settings.json: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // Resolve preset from settings or env
  const presetFromEnv = process.env["OMG_PRESET"] as PresetName | undefined;
  const presetFromSettings = raw._omg?.preset;
  const preset: PresetName = presetFromEnv ?? presetFromSettings ?? "balanced";

  // Create feature flag resolver
  const featureFlags = new FeatureFlagResolver(preset, raw._omg?.features);

  return {
    raw,
    preset,
    featureFlags,
    projectDir: dir,
    settingsPath,
  };
}

/** Get hook registrations from settings.json */
export function getHookRegistrations(settings: Settings): Record<string, string[]> {
  return (settings.hooks as Record<string, string[]> | undefined) ?? {};
}

/** Get allowed tools from settings.json */
export function getAllowedTools(settings: Settings): string[] {
  return settings.permissions?.allow ?? [];
}

/** Get denied tools from settings.json */
export function getDeniedTools(settings: Settings): string[] {
  return settings.permissions?.deny ?? [];
}
