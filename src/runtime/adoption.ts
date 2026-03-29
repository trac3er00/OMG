/**
 * Adoption mode management.
 * Handles OMG-only vs coexist mode, version tracking, preset selection.
 * Mirrors runtime/adoption.py.
 */

import type { PresetName } from "../types/config.js";
import { CANONICAL_VERSION } from "./canonical-taxonomy.js";
import type { AdoptionMode } from "./canonical-taxonomy.js";

export interface AdoptionConfig {
  readonly mode: AdoptionMode;
  readonly preset: PresetName;
  readonly version: string;
  readonly installedAt: string;
  readonly hosts: string[];
}

export const DEFAULT_ADOPTION: AdoptionConfig = {
  mode: "omg-only",
  preset: "balanced",
  version: CANONICAL_VERSION,
  installedAt: new Date().toISOString(),
  hosts: [],
};

export function selectDefaultPreset(mode: AdoptionMode, hostCount: number): PresetName {
  if (mode === "coexist") {
    return "interop";
  }
  if (hostCount === 0) {
    return "safe";
  }
  if (hostCount === 1) {
    return "balanced";
  }
  return "interop";
}

export function needsUpgrade(installedVersion: string): boolean {
  return installedVersion !== CANONICAL_VERSION;
}
