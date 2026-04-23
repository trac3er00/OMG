import { randomBytes } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { OmgDatabase } from "./database.js";
import { StateResolver } from "./state-resolver.js";
import {
  decrypt,
  deriveKey,
  encrypt,
  type EncryptedPayload,
} from "../security/crypto.js";

const DEFAULT_CAPACITY_LIMIT = 10_000;
const DEFAULT_NAMESPACE = "default";
const DEFAULT_SALT = "omg-memory-store-v3-salt";
const STORE_KEY_DERIVE_ITERATIONS = 600_000;
const DEFAULT_DB_FILENAME = "memory.sqlite3";
const MEMORY_SECRET_FILENAME = "memory-store.key";
const MEMORY_SECRET_BYTES = 32;

const PII_PATTERNS: ReadonlyArray<readonly [RegExp, string]> = [
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, "[REDACTED:EMAIL]"],
  [
    /\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b/g,
    "[REDACTED:PHONE]",
  ],
  [/\b\d{3}-\d{2}-\d{4}\b/g, "[REDACTED:SSN]"],
];

interface MemoryRow {
  readonly id: number;
  readonly key: string;
  readonly namespace: string;
  readonly content: string;
  readonly tags_json: string;
  readonly run_id: string | null;
  readonly source_cli: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export class MemoryStoreFullError extends Error {
  constructor(
    limit = DEFAULT_CAPACITY_LIMIT,
    message = `Memory store is full (${limit} items). Delete items before adding new ones.`,
  ) {
    super(message);
    this.name = "MemoryStoreFullError";
  }
}

export interface MemoryEntry {
  readonly key: string;
  readonly namespace: string;
  readonly content: string;
  readonly tags: readonly string[];
  readonly runId?: string;
  readonly sourceCli?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface WriteOptions {
  readonly content: string;
  readonly tags?: readonly string[];
  readonly runId?: string;
  readonly sourceCli?: string;
}

export interface SearchResult {
  readonly key: string;
  readonly rank: number;
}

export interface MemoryStoreConfig {
  readonly projectDir: string;
  readonly namespace?: string;
  readonly passphrase?: string;
  readonly capacityLimit?: number;
  readonly dbFileName?: string;
}

function loadOrCreateStorePassphrase(stateDir: string): string {
  const keyPath = join(stateDir, MEMORY_SECRET_FILENAME);
  if (existsSync(keyPath)) {
    return readFileSync(keyPath, "utf8").trim();
  }

  if (!existsSync(stateDir)) {
    mkdirSync(stateDir, { recursive: true });
  }

  const secret = randomBytes(MEMORY_SECRET_BYTES).toString("hex");
  try {
    // Use exclusive-create flag to prevent TOCTOU race condition.
    // If another process created the file between our existsSync check and now,
    // the 'wx' flag will cause writeFileSync to throw EEXIST.
    writeFileSync(keyPath, secret, { mode: 0o600, flag: "wx" });
    chmodSync(keyPath, 0o600);
    return secret;
  } catch (err: unknown) {
    if (
      err &&
      typeof err === "object" &&
      "code" in err &&
      err.code === "EEXIST"
    ) {
      // Another process won the race - read their secret instead
      return readFileSync(keyPath, "utf8").trim();
    }
    throw err;
  }
}

export class MemoryStore {
  private readonly db: OmgDatabase;
  private readonly namespace: string;
  private readonly passphrase: string;
  private readonly capacityLimit: number;
  private encryptionKey: Buffer | null = null;
  private encryptionKeyPromise: Promise<Buffer> | null = null;

  constructor(config: MemoryStoreConfig) {
    this.namespace =
      (config.namespace ?? DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE;
    this.capacityLimit = Math.max(
      1,
      config.capacityLimit ?? DEFAULT_CAPACITY_LIMIT,
    );

    const resolver = new StateResolver(config.projectDir);
    const configuredPassphrase =
      config.passphrase ?? process.env.OMG_MEMORY_PASSPHRASE;
    this.passphrase =
      configuredPassphrase?.trim() ||
      loadOrCreateStorePassphrase(resolver.stateDir);
    const dbPath = resolver.resolve(config.dbFileName ?? DEFAULT_DB_FILENAME);
    this.db = new OmgDatabase({ path: dbPath, walMode: true });

    this.initSchema();
  }

  private initSchema(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL,
        namespace TEXT NOT NULL DEFAULT 'default',
        content TEXT NOT NULL,
        tags_json TEXT NOT NULL DEFAULT '[]',
        run_id TEXT,
        source_cli TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(key, namespace)
      )
    `);

    this.db.exec(
      "CREATE INDEX IF NOT EXISTS idx_memories_namespace_key ON memories(namespace, key)",
    );

    this.db.exec(`
      CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
      USING fts5(memory_id UNINDEXED, key, content, tags, namespace UNINDEXED)
    `);
  }

  private async getKey(): Promise<Buffer> {
    if (this.encryptionKey !== null) {
      return this.encryptionKey;
    }
    if (this.encryptionKeyPromise === null) {
      this.encryptionKeyPromise = deriveKey(
        this.passphrase,
        DEFAULT_SALT,
        STORE_KEY_DERIVE_ITERATIONS,
      )
        .then((key) => {
          this.encryptionKey = key;
          return key;
        })
        .catch((error) => {
          this.encryptionKeyPromise = null;
          throw error;
        });
    }
    return this.encryptionKeyPromise;
  }

  private redactPii(content: string): string {
    let redacted = content;
    for (const [pattern, token] of PII_PATTERNS) {
      redacted = redacted.replace(pattern, token);
    }
    return redacted;
  }

  private async encryptContent(content: string): Promise<string> {
    const key = await this.getKey();
    return JSON.stringify(encrypt(content, key));
  }

  private async decryptContent(stored: string): Promise<string> {
    const key = await this.getKey();
    const payload = JSON.parse(stored) as EncryptedPayload;
    return decrypt(payload, key);
  }

  private parseTags(raw: string): string[] {
    try {
      const value = JSON.parse(raw) as unknown;
      if (!Array.isArray(value)) {
        return [];
      }
      return value.map((entry) => String(entry));
    } catch {
      return [];
    }
  }

  private toEntry(row: MemoryRow, content: string): MemoryEntry {
    // exactOptionalPropertyTypes: don't assign undefined to optional properties
    const entry: MemoryEntry = {
      key: row.key,
      namespace: row.namespace,
      content,
      tags: this.parseTags(row.tags_json),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      // Spread optional fields only when present
      ...(row.run_id != null ? { runId: row.run_id } : {}),
      ...(row.source_cli != null ? { sourceCli: row.source_cli } : {}),
    };
    return entry;
  }

  private upsertFts(
    memoryId: number,
    key: string,
    content: string,
    tags: readonly string[],
  ): void {
    this.db.run("DELETE FROM memories_fts WHERE memory_id = ?", [memoryId]);
    this.db.run(
      "INSERT INTO memories_fts (memory_id, key, content, tags, namespace) VALUES (?, ?, ?, ?, ?)",
      [memoryId, key, content, tags.join(" "), this.namespace],
    );
  }

  async write(key: string, options: WriteOptions): Promise<MemoryEntry> {
    const existing = this.db.get<{ id: number; created_at: string }>(
      "SELECT id, created_at FROM memories WHERE key = ? AND namespace = ?",
      [key, this.namespace],
    );
    if (!existing) {
      const row = this.db.get<{ n: number }>(
        "SELECT COUNT(*) AS n FROM memories WHERE namespace = ?",
        [this.namespace],
      );
      if ((row?.n ?? 0) >= this.capacityLimit) {
        throw new MemoryStoreFullError(this.capacityLimit);
      }
    }

    const redacted = this.redactPii(options.content);
    const encrypted = await this.encryptContent(redacted);
    const tags = options.tags ? [...options.tags] : [];
    const tagsJson = JSON.stringify(tags);
    const now = new Date().toISOString();
    const createdAt = existing?.created_at ?? now;

    this.db.run(
      `
      INSERT INTO memories (key, namespace, content, tags_json, run_id, source_cli, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(key, namespace) DO UPDATE SET
        content = excluded.content,
        tags_json = excluded.tags_json,
        run_id = excluded.run_id,
        source_cli = excluded.source_cli,
        updated_at = excluded.updated_at
      `,
      [
        key,
        this.namespace,
        encrypted,
        tagsJson,
        options.runId ?? null,
        options.sourceCli ?? null,
        createdAt,
        now,
      ],
    );

    const row = this.db.get<MemoryRow>(
      "SELECT id, key, namespace, content, tags_json, run_id, source_cli, created_at, updated_at FROM memories WHERE key = ? AND namespace = ?",
      [key, this.namespace],
    );

    if (!row) {
      throw new Error("Memory write succeeded but row could not be read back.");
    }

    this.upsertFts(row.id, row.key, redacted, tags);

    return this.toEntry(row, redacted);
  }

  async read(key: string): Promise<MemoryEntry | null> {
    const row = this.db.get<MemoryRow>(
      "SELECT id, key, namespace, content, tags_json, run_id, source_cli, created_at, updated_at FROM memories WHERE key = ? AND namespace = ?",
      [key, this.namespace],
    );

    if (!row) {
      return null;
    }

    const content = await this.decryptContent(row.content);
    return this.toEntry(row, content);
  }

  async delete(key: string): Promise<boolean> {
    const row = this.db.get<{ id: number }>(
      "SELECT id FROM memories WHERE key = ? AND namespace = ?",
      [key, this.namespace],
    );
    if (!row) {
      return false;
    }

    this.db.run("DELETE FROM memories WHERE id = ?", [row.id]);
    this.db.run("DELETE FROM memories_fts WHERE memory_id = ?", [row.id]);
    return true;
  }

  async listKeys(prefix = ""): Promise<string[]> {
    const rows = this.db.all<{ key: string }>(
      prefix.length > 0
        ? "SELECT key FROM memories WHERE namespace = ? AND key LIKE ? ORDER BY key"
        : "SELECT key FROM memories WHERE namespace = ? ORDER BY key",
      prefix.length > 0 ? [this.namespace, `${prefix}%`] : [this.namespace],
    );
    return rows.map((row) => row.key);
  }

  async search(query: string, limit = 10): Promise<SearchResult[]> {
    const boundedLimit = Math.max(1, Math.min(limit, 200));
    try {
      return this.db.all<SearchResult>(
        `
        SELECT key, bm25(memories_fts) AS rank
        FROM memories_fts
        WHERE memories_fts MATCH ?
          AND namespace = ?
        ORDER BY rank ASC
        LIMIT ?
        `,
        [query, this.namespace, boundedLimit],
      );
    } catch {
      return [];
    }
  }

  async count(): Promise<number> {
    const row = this.db.get<{ n: number }>(
      "SELECT COUNT(*) AS n FROM memories WHERE namespace = ?",
      [this.namespace],
    );
    return row?.n ?? 0;
  }

  getRawDb(): OmgDatabase {
    return this.db;
  }

  close(): void {
    this.db.close();
  }
}
