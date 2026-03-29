/**
 * Trust Review — config change risk scoring + Ed25519-signed trust manifests.
 *
 * Ported from hooks/trust_review.py with upgrade from SHA-256 hashing
 * to Ed25519 cryptographic signing for manifest integrity.
 */
import { sign, verify, hash } from "./crypto.js";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";
import type { KeyObject } from "node:crypto";

export interface TrustChangeEvent {
  readonly type: string;
  readonly count: number;
}

export interface TrustManifestFileEntry {
  readonly path: string;
  readonly hash: string;
}

export interface TrustManifest {
  readonly version: number;
  readonly digest: string;
  readonly signature: string;
  readonly files: ReadonlyArray<TrustManifestFileEntry>;
  readonly createdAt: string;
}

export interface TrustReviewConfig {
  readonly projectDir: string;
  readonly privateKey?: KeyObject;
  readonly publicKey?: KeyObject;
}

export type TrustDecision = "deny" | "ask" | "allow";

const CHANGE_SCORES: Record<string, number> = {
  mcp_server_added: 50,
  mcp_server_modified: 40,
  hook_added: 30,
  hook_modified: 20,
  env_permission_added: 60,
  permission_scope_expanded: 70,
  description_changed: 5,
  unknown: 25,
};

/**
 * Score a single trust-relevant change event.
 *
 * Base score comes from the change type; multiplied by count (capped at 3).
 */
export function scoreTrustChange(event: TrustChangeEvent): number {
  const baseScore = CHANGE_SCORES[event.type] ?? CHANGE_SCORES["unknown"]!;
  return baseScore * Math.min(event.count, 3);
}

/**
 * Map a cumulative risk score to a trust decision.
 *
 * - score >= 80 → deny  (critical risk, block automatically)
 * - score >= 45 → ask   (high risk, require human approval)
 * - score <  45 → allow (acceptable risk)
 */
export function getTrustDecision(totalScore: number): TrustDecision {
  if (totalScore >= 80) return "deny";
  if (totalScore >= 45) return "ask";
  return "allow";
}

export class TrustReviewManager {
  private readonly manifestPath: string;
  private readonly privateKey: KeyObject | undefined;
  private readonly publicKey: KeyObject | undefined;

  constructor(config: TrustReviewConfig) {
    const resolver = new StateResolver(config.projectDir);
    // trust/ lives next to state/ → go up from .omg/state to .omg/trust
    this.manifestPath = resolver.resolve(join("..", "trust", "manifest.lock.json"));
    this.privateKey = config.privateKey;
    this.publicKey = config.publicKey;
  }

  /**
   * Build a trust manifest from a set of file contents, sign it with Ed25519,
   * and persist it atomically.
   */
  async generateManifest(files: Record<string, string>): Promise<TrustManifest> {
    const fileEntries: TrustManifestFileEntry[] = Object.entries(files).map(
      ([path, content]) => ({
        path,
        hash: hash(content),
      }),
    );

    const digest = hash(JSON.stringify(fileEntries));
    const digestBuf = Buffer.from(digest, "utf8");

    let signature = "";
    if (this.privateKey) {
      signature = sign(digestBuf, this.privateKey).toString("hex");
    }

    const manifest: TrustManifest = {
      version: 1,
      digest,
      signature,
      files: fileEntries,
      createdAt: new Date().toISOString(),
    };

    atomicWriteJson(this.manifestPath, manifest);
    return manifest;
  }

  /**
   * Verify a manifest's Ed25519 signature against the stored public key.
   * Returns false if signature is missing, public key is absent, or
   * the signature does not match the digest.
   */
  async verifyManifest(manifest: TrustManifest): Promise<boolean> {
    if (!manifest.signature || !this.publicKey) return false;

    try {
      const digestBuf = Buffer.from(manifest.digest, "utf8");
      const sigBuf = Buffer.from(manifest.signature, "hex");
      return verify(digestBuf, sigBuf, this.publicKey);
    } catch {
      return false;
    }
  }

  loadManifest(): TrustManifest | undefined {
    return readJsonFile<TrustManifest>(this.manifestPath);
  }
}
