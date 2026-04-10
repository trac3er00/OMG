import {
  MemoryStore,
  type MemoryEntry,
  type MemoryStoreConfig,
  type WriteOptions,
} from "./memory-store.js";
import { type OmgDatabase } from "./database.js";

const DEFAULT_DSS_NAMESPACE = "dss";
const DEFAULT_DSS_DB_FILENAME = "dss.sqlite3";

export { MemoryStoreFullError } from "./memory-store.js";

export interface DssConfig extends MemoryStoreConfig {
  readonly namespace?: string;
  readonly dbFileName?: string;
}

export interface DssEntry<T = unknown> {
  readonly key: string;
  readonly namespace: string;
  readonly value: T;
  readonly tags: readonly string[];
  readonly runId?: string;
  readonly sourceCli?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface DssSetOptions extends Omit<WriteOptions, "content"> {}

export interface DssImportResult {
  readonly imported: number;
}

export class DSS {
  private readonly store: MemoryStore;

  constructor(config: DssConfig) {
    this.store = new MemoryStore({
      ...config,
      namespace:
        (config.namespace ?? DEFAULT_DSS_NAMESPACE).trim() ||
        DEFAULT_DSS_NAMESPACE,
      dbFileName: config.dbFileName ?? DEFAULT_DSS_DB_FILENAME,
    });
  }

  private serializeValue(value: unknown): string {
    if (typeof value === "string") {
      return value;
    }

    return JSON.stringify(value);
  }

  private deserializeValue<T>(content: string): T {
    try {
      return JSON.parse(content) as T;
    } catch {
      return content as T;
    }
  }

  private toEntry<T>(entry: MemoryEntry): DssEntry<T> {
    return {
      key: entry.key,
      namespace: entry.namespace,
      value: this.deserializeValue<T>(entry.content),
      tags: entry.tags,
      createdAt: entry.createdAt,
      updatedAt: entry.updatedAt,
      ...(entry.runId != null ? { runId: entry.runId } : {}),
      ...(entry.sourceCli != null ? { sourceCli: entry.sourceCli } : {}),
    };
  }

  async get<T = unknown>(key: string): Promise<DssEntry<T> | null> {
    const entry = await this.store.read(key);
    return entry ? this.toEntry<T>(entry) : null;
  }

  async set<T = unknown>(
    key: string,
    value: T,
    options: DssSetOptions = {},
  ): Promise<DssEntry<T>> {
    const entry = await this.store.write(key, {
      ...options,
      content: this.serializeValue(value),
    });
    return this.toEntry<T>(entry);
  }

  async delete(key: string): Promise<boolean> {
    return this.store.delete(key);
  }

  async list<T = unknown>(prefix = ""): Promise<DssEntry<T>[]> {
    const keys = await this.store.listKeys(prefix);
    const entries = await Promise.all(
      keys.map(async (key) => this.get<T>(key)),
    );
    return entries.filter((entry): entry is DssEntry<T> => entry !== null);
  }

  async clear(): Promise<number> {
    const keys = await this.store.listKeys();
    let deleted = 0;
    for (const key of keys) {
      if (await this.store.delete(key)) {
        deleted += 1;
      }
    }
    return deleted;
  }

  async compact(): Promise<void> {
    const db = this.store.getRawDb();
    db.exec(
      "DELETE FROM memories_fts WHERE memory_id NOT IN (SELECT id FROM memories)",
    );
    db.exec("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')");
    db.exec("PRAGMA wal_checkpoint(TRUNCATE)");
    db.exec("VACUUM");
  }

  async export<T = unknown>(): Promise<DssEntry<T>[]> {
    return this.list<T>();
  }

  async import<T = unknown>(
    entries: readonly DssEntry<T>[],
  ): Promise<DssImportResult> {
    for (const entry of entries) {
      await this.set(entry.key, entry.value, {
        tags: entry.tags,
        ...(entry.runId != null ? { runId: entry.runId } : {}),
        ...(entry.sourceCli != null ? { sourceCli: entry.sourceCli } : {}),
      });
    }

    return { imported: entries.length };
  }

  getRawDb(): OmgDatabase {
    return this.store.getRawDb();
  }

  close(): void {
    this.store.close();
  }
}
