import { existsSync } from "node:fs";
import { join } from "node:path";
import type { StateResolver } from "../interfaces/state.js";
import type { HostType } from "../types/config.js";
import { CANONICAL_VERSION } from "./canonical-taxonomy.js";

const CANONICAL_HOSTS: readonly HostType[] = ["claude", "codex", "gemini", "kimi"];
const COMPATIBILITY_ONLY_HOSTS: readonly HostType[] = ["opencode"];
const SUPERPOWERS_SENTINELS: readonly string[][] = [
  ["skills", "brainstorming"],
  ["commands", "superpowers.md"],
  ["commands", "superpower.md"],
];

export type LegacyEcosystem = "omc" | "omx" | "superpowers";

export interface CompatibilityInfo {
  readonly host: HostType;
  readonly requestedVersion: string;
  readonly runtimeVersion: string;
  readonly compatibility: "canonical" | "compatibility-only" | "unsupported";
  readonly compatible: boolean;
  readonly reasons: readonly string[];
  readonly legacyEcosystems: readonly LegacyEcosystem[];
}

export interface CompatLayerDependencies {
  readonly projectDir: string;
  readonly stateResolver?: StateResolver;
  readonly pathExists?: (path: string) => boolean;
}

function majorVersion(version: string): number | null {
  const major = Number.parseInt(version.split(".")[0] ?? "", 10);
  return Number.isNaN(major) ? null : major;
}

function detectLegacyEcosystems(projectDir: string, pathExists: (path: string) => boolean): LegacyEcosystem[] {
  const detected: LegacyEcosystem[] = [];

  if (pathExists(join(projectDir, ".omc"))) {
    detected.push("omc");
  }
  if (pathExists(join(projectDir, ".omx"))) {
    detected.push("omx");
  }

  const claudeDir = pathExists(join(projectDir, ".claude")) ? join(projectDir, ".claude") : projectDir;
  if (SUPERPOWERS_SENTINELS.some((segments) => pathExists(join(claudeDir, ...segments)))) {
    detected.push("superpowers");
  }

  return detected;
}

export class CompatLayer {
  private readonly projectDir: string;

  private readonly stateResolver: StateResolver | undefined;

  private readonly pathExists: (path: string) => boolean;

  public constructor(dependencies: CompatLayerDependencies) {
    this.projectDir = dependencies.projectDir;
    this.stateResolver = dependencies.stateResolver;
    this.pathExists = dependencies.pathExists ?? existsSync;
  }

  public resolveCompat(host: HostType, version: string): CompatibilityInfo {
    const reasons: string[] = [];
    const hostCompatibility = CANONICAL_HOSTS.includes(host)
      ? "canonical"
      : COMPATIBILITY_ONLY_HOSTS.includes(host)
        ? "compatibility-only"
        : "unsupported";

    if (hostCompatibility === "compatibility-only") {
      reasons.push(`host '${host}' is compatibility-only`);
    }
    if (hostCompatibility === "unsupported") {
      reasons.push(`host '${host}' is not supported`);
    }

    const requestedMajor = majorVersion(version);
    const runtimeMajor = majorVersion(CANONICAL_VERSION);
    if (requestedMajor === null || runtimeMajor === null || requestedMajor !== runtimeMajor) {
      reasons.push(`version mismatch: requested ${version}, runtime ${CANONICAL_VERSION}`);
    }

    if (this.stateResolver) {
      const statePath = this.stateResolver.resolvePath("compat");
      if (statePath.length === 0) {
        reasons.push("state resolver returned empty compat path");
      }
    }

    return {
      host,
      requestedVersion: version,
      runtimeVersion: CANONICAL_VERSION,
      compatibility: hostCompatibility,
      compatible: reasons.length === 0 || (hostCompatibility === "compatibility-only" && reasons.length === 1),
      reasons,
      legacyEcosystems: detectLegacyEcosystems(this.projectDir, this.pathExists),
    };
  }
}
