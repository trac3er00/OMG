import { Database, type SQLQueryBindings } from "bun:sqlite";
import { existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

export interface DatabaseConfig {
  readonly path: string;
  readonly walMode?: boolean;
  readonly readOnly?: boolean;
}

export interface FtsSearchResult {
  readonly key: string;
  readonly rank: number;
}

export interface Migration {
  readonly id: string;
  readonly sql: string;
}

export class OmgDatabase {
  private readonly db: Database;

  constructor(config: DatabaseConfig) {
    if (config.path !== ":memory:") {
      const dir = dirname(config.path);
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
      }
    }

    this.db = new Database(config.path, {
      readonly: config.readOnly ?? false,
      create: true,
    });

    if (config.walMode !== false && config.path !== ":memory:") {
      this.db.exec("PRAGMA journal_mode=WAL");
      this.db.exec("PRAGMA synchronous=NORMAL");
    }

    this.db.exec("PRAGMA foreign_keys=ON");
    this.db.exec(
      `
      CREATE TABLE IF NOT EXISTS _migrations (
        id TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
      )
      `,
    );
  }

  exec(sql: string): void {
    this.db.exec(sql);
  }

  run(sql: string, params: readonly SQLQueryBindings[] = []): { changes: number; lastInsertRowid: number } {
    const stmt = this.db.prepare(sql);
    const result = stmt.run(...params);
    return {
      changes: result.changes,
      lastInsertRowid: Number(result.lastInsertRowid),
    };
  }

  all<T = Record<string, unknown>>(sql: string, params: readonly SQLQueryBindings[] = []): T[] {
    const stmt = this.db.prepare(sql);
    return stmt.all(...params) as T[];
  }

  get<T = Record<string, unknown>>(sql: string, params: readonly SQLQueryBindings[] = []): T | undefined {
    const stmt = this.db.prepare(sql);
    return stmt.get(...params) as T | undefined;
  }

  transaction<T>(fn: () => T): T {
    return this.db.transaction(fn)();
  }

  migrate(migrations: readonly Migration[]): void {
    this.transaction(() => {
      for (const migration of migrations) {
        const alreadyApplied = this.get<{ id: string }>("SELECT id FROM _migrations WHERE id = ?", [migration.id]);
        if (alreadyApplied) {
          continue;
        }
        this.exec(migration.sql);
        this.run("INSERT INTO _migrations(id) VALUES (?)", [migration.id]);
      }
    });
  }

  createFts5Table(tableName: string, columns: readonly string[], tokenizer = "porter ascii"): void {
    const cols = columns.join(", ");
    this.exec(`
      CREATE VIRTUAL TABLE IF NOT EXISTS ${tableName}
      USING fts5(${cols}, tokenize = '${tokenizer}')
    `);
  }

  ftsSearch(tableName: string, keyColumn: string, query: string, limit = 20): FtsSearchResult[] {
    return this.all<FtsSearchResult>(
      `
      SELECT ${keyColumn} as key, bm25(${tableName}) as rank
      FROM ${tableName}
      WHERE ${tableName} MATCH ?
      ORDER BY rank ASC
      LIMIT ?
      `,
      [query, limit],
    );
  }

  getAppliedMigrations(): string[] {
    return this.all<{ id: string }>("SELECT id FROM _migrations ORDER BY applied_at ASC, id ASC").map((row) => row.id);
  }

  getJournalMode(): string {
    const row = this.get<{ journal_mode: string }>("PRAGMA journal_mode");
    return row?.journal_mode ?? "unknown";
  }

  close(): void {
    this.db.close();
  }

  static open(path: string): OmgDatabase {
    return new OmgDatabase({ path, walMode: true });
  }

  static memory(): OmgDatabase {
    return new OmgDatabase({ path: ":memory:", walMode: false });
  }
}
