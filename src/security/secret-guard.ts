import type { SecretGuardResult } from "../interfaces/security.js";
import { appendJsonLine } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";

/**
 * Patterns that match secret / credential files.
 * Ported from hooks/secret-guard.py → policy_engine file patterns.
 */
const SECRET_FILE_PATTERNS: readonly RegExp[] = [
  /^\.env($|\.|\/)/i,
  /\.env\.(local|production|staging|development|test)$/i,
  /(^|\/)\.aws\//,
  /id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$/,
  /credentials\.(json|yml|yaml)$/i,
  /\.pem$|\.key$|\.p12$|\.pfx$/i,
  /(^|\/)keystore\./i,
  /\.netrc$/,
  /(^|\/)secrets\.ya?ml$/i,
];

export interface SecretGuardConfig {
  readonly projectDir: string;
  readonly allowlist?: readonly string[];
}

export class SecretGuard {
  private readonly resolver: StateResolver;
  private readonly allowlist: ReadonlySet<string>;
  private readonly auditPath: string;

  constructor(config: SecretGuardConfig) {
    this.resolver = new StateResolver(config.projectDir);
    this.allowlist = new Set(config.allowlist ?? []);
    this.auditPath = this.resolver.resolve(join("ledger", "secret-access.jsonl"));
  }

  async evaluateFileAccess(tool: string, filePath: string): Promise<SecretGuardResult> {
    const normalized = filePath.replace(/\\/g, "/");

    // Allowlist bypass
    if (this.allowlist.has(filePath) || this.allowlist.has(normalized)) {
      return {
        allowed: true,
        reason: "File is allowlisted",
        tool,
        filePath,
        allowlisted: true,
        auditLogged: false,
      };
    }

    const isSecret = SECRET_FILE_PATTERNS.some((p) => p.test(normalized));

    if (isSecret) {
      const entry = {
        timestamp: new Date().toISOString(),
        event: "secret_access_blocked",
        tool,
        filePath,
        allowed: false,
      };
      let auditLogged = false;
      try {
        appendJsonLine(this.auditPath, entry);
        auditLogged = true;
      } catch {
        // best-effort audit logging
      }
      return {
        allowed: false,
        reason: `Access to secret file '${filePath}' blocked`,
        tool,
        filePath,
        allowlisted: false,
        auditLogged,
      };
    }

    return {
      allowed: true,
      reason: "File access allowed",
      tool,
      filePath,
      allowlisted: false,
      auditLogged: false,
    };
  }
}
