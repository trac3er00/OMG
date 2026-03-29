import type { MutationOperation, PolicyDecision } from "./policy.js";

export interface MutationCheck {
  readonly allowed: boolean;
  readonly reason: string;
  readonly operation: MutationOperation;
  readonly decision: PolicyDecision;
  readonly exemption?: string;
  readonly riskScore: number;
}

export interface SecretGuardResult {
  readonly allowed: boolean;
  readonly reason: string;
  readonly tool: string;
  readonly filePath: string;
  readonly allowlisted: boolean;
  readonly auditLogged: boolean;
}

export interface CredentialEntry {
  readonly provider: string;
  readonly key: string;
  readonly encryptedValue: string;
  readonly createdAt: string;
  readonly expiresAt?: string;
  readonly usageCount: number;
  readonly lastUsed?: string;
}

export interface TrustManifest {
  readonly digest: string;
  readonly signature: string;
  readonly publicKeyId: string;
  readonly files: ReadonlyArray<{ path: string; hash: string }>;
  readonly createdAt: string;
}

export interface InjectionDetectionResult {
  readonly detected: boolean;
  readonly confidence: number;
  readonly patterns: readonly string[];
  readonly sanitizedContent: string;
  readonly quarantined: readonly string[];
}


