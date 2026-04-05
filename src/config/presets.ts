/**
 * OMG preset configurations.
 * Each preset enables/disables specific features for different use cases.
 */

import type { PresetName, PresetConfig, FeatureFlags } from "../types/config.js";

export const PRESET_CONFIGS: Record<PresetName, PresetConfig> = {
  safe: {
    name: "safe",
    description: "Minimal footprint — mutation gate, firewall, secret guard only",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": false,
      "tdd-gate": false,
      "trust-review": false,
      "auto-compact": false,
      "hud": false,
      "browser": false,
      "team-dispatch": false,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate"],
  },

  balanced: {
    name: "balanced",
    description: "Standard governance — recommended for most users",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": false,
      "trust-review": true,
      "auto-compact": true,
      "hud": true,
      "browser": false,
      "team-dispatch": false,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate", "proof-gate", "trust-review"],
  },

  interop: {
    name: "interop",
    description: "Multi-host coexistence mode",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": false,
      "trust-review": true,
      "auto-compact": true,
      "hud": true,
      "browser": false,
      "team-dispatch": true,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate", "proof-gate", "trust-review", "team-dispatch"],
  },

  labs: {
    name: "labs",
    description: "Experimental features enabled — for power users",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": true,
      "trust-review": true,
      "auto-compact": true,
      "hud": true,
      "browser": true,
      "team-dispatch": true,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate", "proof-gate", "trust-review", "tdd-gate"],
  },

  buffet: {
    name: "buffet",
    description: "All features enabled — pick what you want",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": true,
      "trust-review": true,
      "auto-compact": true,
      "hud": true,
      "browser": true,
      "team-dispatch": true,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate", "proof-gate", "trust-review", "tdd-gate"],
  },

  production: {
    name: "production",
    description: "Full governance for production environments",
    features: {
      "mutation-gate": true,
      "firewall": true,
      "secret-guard": true,
      "cost-ledger": true,
      "proof-gate": true,
      "tdd-gate": true,
      "trust-review": true,
      "auto-compact": true,
      "hud": true,
      "browser": false,
      "team-dispatch": true,
    },
    hooks: ["firewall", "secret-guard", "mutation-gate", "proof-gate", "trust-review", "tdd-gate"],
  },
};

export function getPresetConfig(preset: PresetName): PresetConfig {
  const config = PRESET_CONFIGS[preset];
  if (!config) throw new Error(`Unknown preset: ${preset}`);
  return config;
}

export function getPresetFeatures(preset: PresetName): FeatureFlags {
  return getPresetConfig(preset).features;
}
