import type { RiskLevel } from "./policy.js";

export interface DefenseState {
  readonly riskLevel: RiskLevel;
  readonly injectionHits: number;
  readonly contaminationScore: number;
  readonly overthinkingScore: number;
  readonly prematureFixerScore: number;
  readonly actions: readonly string[];
  readonly reasons: readonly string[];
  readonly updatedAt: string;
}

export type TrustTier = "local" | "balanced" | "research" | "browser";

export interface TrustState {
  readonly active: boolean;
  readonly lastSourceType: string;
  readonly lastTrustTier: TrustTier;
  readonly trustScore: number;
}

export interface ContextPacket {
  readonly packetVersion: string;
  readonly summary: string;
  readonly artifactPointers: readonly string[];
  readonly provenancePointers: readonly string[];
  readonly governance: Readonly<Record<string, unknown>>;
  readonly runId: string;
  readonly deltaOnly: boolean;
}

export interface StateResolver {
  readonly projectDir: string;
  resolvePath(key: string): string;
}

export interface ProfileDigest {
  readonly architectureRequests: readonly string[];
  readonly constraints: readonly string[];
  readonly tags: readonly string[];
  readonly summary: string;
  readonly confidence: number;
}
