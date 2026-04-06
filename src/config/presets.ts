/**
 * OMG preset configurations.
 * Each preset enables/disables specific features for different use cases.
 */

import type {
  PresetName,
  PresetConfig,
  FeatureFlags,
} from "../types/config.js";

const BASE_PRESET_CONFIGS = {
  safe: {
    name: "safe",
    description:
      "Minimal footprint — mutation gate, firewall, secret guard only",
    features: {
      "mutation-gate": true,
      firewall: true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": false,
      "tdd-gate": false,
      "trust-review": false,
      "auto-compact": false,
      hud: false,
      browser: false,
      "team-dispatch": false,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate"],
  },

  balanced: {
    name: "balanced",
    description: "Standard governance — recommended for most users",
    features: {
      "mutation-gate": true,
      firewall: true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": false,
      "trust-review": true,
      "auto-compact": true,
      hud: true,
      browser: false,
      "team-dispatch": false,
    },
    hooks: [
      "firewall",
      "secret-guard",
      "mutation-gate",
      "proof-gate",
      "trust-review",
    ],
  },

  interop: {
    name: "interop",
    description: "Multi-host coexistence mode",
    features: {
      "mutation-gate": true,
      firewall: true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": false,
      "trust-review": true,
      "auto-compact": true,
      hud: true,
      browser: false,
      "team-dispatch": true,
    },
    hooks: [
      "firewall",
      "secret-guard",
      "mutation-gate",
      "proof-gate",
      "trust-review",
      "team-dispatch",
    ],
  },

  labs: {
    name: "labs",
    description: "Experimental features enabled — for power users",
    features: {
      "mutation-gate": true,
      firewall: true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": true,
      "trust-review": true,
      "auto-compact": true,
      hud: true,
      browser: true,
      "team-dispatch": true,
    },
    hooks: [
      "firewall",
      "secret-guard",
      "mutation-gate",
      "proof-gate",
      "trust-review",
      "tdd-gate",
    ],
  },

  production: {
    name: "production",
    description: "Full governance for production environments",
    features: {
      "mutation-gate": true,
      firewall: true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": true,
      "trust-review": true,
      "auto-compact": true,
      hud: true,
      browser: false,
      "team-dispatch": true,
    },
    hooks: [
      "firewall",
      "secret-guard",
      "mutation-gate",
      "proof-gate",
      "trust-review",
      "tdd-gate",
    ],
  },
} as const satisfies Record<
  "safe" | "balanced" | "interop" | "labs" | "production",
  PresetConfig
>;

export const DEPRECATED_PRESETS: Record<string, string> = {
  safe: "minimal",
  balanced: "standard",
  interop: "full",
  labs: "experimental",
  buffet: "production",
};

const WARNED_PRESETS = new Set<string>();

export const PRESET_CONFIGS: Record<PresetName, PresetConfig> = {
  ...BASE_PRESET_CONFIGS,
  minimal: BASE_PRESET_CONFIGS.safe,
  standard: BASE_PRESET_CONFIGS.balanced,
  full: BASE_PRESET_CONFIGS.interop,
  experimental: BASE_PRESET_CONFIGS.labs,
  production: BASE_PRESET_CONFIGS.production,
  buffet: BASE_PRESET_CONFIGS.production,
};

export function normalizePresetName(preset: PresetName): PresetName {
  const next = DEPRECATED_PRESETS[preset];
  if (!next) {
    return preset;
  }

  if (!WARNED_PRESETS.has(preset)) {
    WARNED_PRESETS.add(preset);
    console.warn(`Preset '${preset}' is deprecated. Use '${next}' instead.`);
  }

  return next as PresetName;
}

export function getPresetConfig(preset: PresetName): PresetConfig {
  const config = PRESET_CONFIGS[normalizePresetName(preset)];
  if (!config) throw new Error(`Unknown preset: ${preset}`);
  return config;
}

export function getPresetFeatures(preset: PresetName): FeatureFlags {
  return getPresetConfig(preset).features;
}
