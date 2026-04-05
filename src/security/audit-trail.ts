import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { appendJsonLine } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";

export interface AuditEntryInput {
  readonly actor: string;
  readonly action: string;
  readonly details?: Readonly<Record<string, unknown>>;
}

export interface AuditLogEntry {
  readonly id: string;
  readonly actor: string;
  readonly action: string;
  readonly details?: Readonly<Record<string, unknown>>;
  readonly timestamp: string;
  readonly signature: string;
}

export interface AuditTrailOptions {
  readonly projectDir?: string;
  readonly secret?: string;
}

export const HMAC_KEY_FILENAME = "audit-hmac.key";
const HMAC_KEY_BYTES = 32;

/**
 * Load an existing HMAC key from disk or generate and persist a new one.
 * Key file is written with mode 0600 (owner read/write only).
 */
function loadOrCreateHmacKey(stateDir: string): string {
  const keyPath = join(stateDir, HMAC_KEY_FILENAME);

  if (existsSync(keyPath)) {
    return readFileSync(keyPath, "utf8").trim();
  }

  const key = randomBytes(HMAC_KEY_BYTES).toString("hex");

  if (!existsSync(stateDir)) {
    mkdirSync(stateDir, { recursive: true });
  }

  writeFileSync(keyPath, key, { mode: 0o600 });
  // Ensure permissions even if umask weakened them
  chmodSync(keyPath, 0o600);

  return key;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableJson(item)).join(",")}]`;
  }

  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>).sort(
      ([a], [b]) => a.localeCompare(b),
    );
    return `{${entries.map(([key, child]) => `${JSON.stringify(key)}:${stableJson(child)}`).join(",")}}`;
  }

  return JSON.stringify(value);
}

export class AuditTrail {
  private readonly secret: string;
  private readonly auditFilePath: string;

  private constructor(options: AuditTrailOptions = {}) {
    const resolver = new StateResolver(options.projectDir);
    this.auditFilePath = join(resolver.layout().ledger, "audit.jsonl");
    this.secret =
      options.secret ??
      process.env.OMG_AUDIT_HMAC_SECRET ??
      loadOrCreateHmacKey(resolver.stateDir);
  }

  static create(options: AuditTrailOptions = {}): AuditTrail {
    return new AuditTrail(options);
  }

  static rotateKey(options: { projectDir?: string } = {}): {
    keyPath: string;
    backupPath: string | null;
  } {
    const resolver = new StateResolver(options.projectDir);
    const keyPath = join(resolver.stateDir, HMAC_KEY_FILENAME);
    let backupPath: string | null = null;

    if (existsSync(keyPath)) {
      backupPath = `${keyPath}.${Date.now()}.bak`;
      renameSync(keyPath, backupPath);
    }

    const key = randomBytes(HMAC_KEY_BYTES).toString("hex");

    if (!existsSync(resolver.stateDir)) {
      mkdirSync(resolver.stateDir, { recursive: true });
    }

    writeFileSync(keyPath, key, { mode: 0o600 });
    chmodSync(keyPath, 0o600);

    return { keyPath, backupPath };
  }

  record(entry: AuditEntryInput): AuditLogEntry {
    if (!entry.actor.trim()) {
      throw new Error("audit entry actor must be non-empty");
    }
    if (!entry.action.trim()) {
      throw new Error("audit entry action must be non-empty");
    }

    const unsigned = {
      id: randomBytes(16).toString("hex"),
      actor: entry.actor,
      action: entry.action,
      ...(entry.details ? { details: entry.details } : {}),
      timestamp: new Date().toISOString(),
    };

    const signature = this.sign(unsigned);
    const signedEntry: AuditLogEntry = {
      ...unsigned,
      signature,
    };

    appendJsonLine(this.auditFilePath, signedEntry);
    return signedEntry;
  }

  verify(entry: AuditLogEntry): boolean {
    const expected = this.sign({
      id: entry.id,
      actor: entry.actor,
      action: entry.action,
      ...(entry.details ? { details: entry.details } : {}),
      timestamp: entry.timestamp,
    });

    const expectedBuffer = Buffer.from(expected, "hex");
    const actualBuffer = Buffer.from(entry.signature, "hex");
    if (expectedBuffer.length !== actualBuffer.length) {
      return false;
    }
    return timingSafeEqual(expectedBuffer, actualBuffer);
  }

  private sign(unsignedEntry: Omit<AuditLogEntry, "signature">): string {
    return createHmac("sha256", this.secret)
      .update(stableJson(unsignedEntry), "utf8")
      .digest("hex");
  }
}
