import { afterEach, describe, expect, test } from "bun:test";
import { rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { OmgDatabase, type Migration } from "./database.js";

const cleanupPaths: string[] = [];

afterEach(() => {
  for (const path of cleanupPaths.splice(0, cleanupPaths.length)) {
    rmSync(path, { force: true, recursive: true });
  }
});

describe("OmgDatabase", () => {
  test("creates in-memory database", () => {
    const db = OmgDatabase.memory();
    expect(db).toBeDefined();
    expect(db.getJournalMode()).toBe("memory");
    db.close();
  });

  test("exec and run create and insert rows", () => {
    const db = OmgDatabase.memory();
    db.exec("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)");
    db.run("INSERT INTO test (name) VALUES (?)", ["hello"]);
    const rows = db.all<{ name: string }>("SELECT name FROM test");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.name).toBe("hello");
    db.close();
  });

  test("FTS5 search works", () => {
    const db = OmgDatabase.memory();
    db.createFts5Table("docs", ["key", "content"]);
    db.run("INSERT INTO docs VALUES (?, ?)", ["k1", "hello world orchestration"]);
    db.run("INSERT INTO docs VALUES (?, ?)", ["k2", "security firewall protection"]);
    db.run("INSERT INTO docs VALUES (?, ?)", ["k3", "agent routing dispatch"]);

    const results = db.ftsSearch("docs", "key", "orchestr*");
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((r) => r.key === "k1")).toBe(true);
    db.close();
  });

  test("FTS5 non-matching query returns empty", () => {
    const db = OmgDatabase.memory();
    db.createFts5Table("docs2", ["key", "content"]);
    db.run("INSERT INTO docs2 VALUES (?, ?)", ["k1", "hello world"]);
    const results = db.ftsSearch("docs2", "key", "xyznonexistent");
    expect(results).toHaveLength(0);
    db.close();
  });

  test("rejects unsafe FTS identifiers", () => {
    const db = OmgDatabase.memory();
    expect(() => db.createFts5Table('docs; DROP TABLE _migrations; --', ["key", "content"])).toThrow(
      /Invalid SQLite identifier/,
    );
    expect(() => db.ftsSearch("docs", 'key FROM docs; --', "query")).toThrow(
      /Invalid SQLite identifier/,
    );
    db.close();
  });

  test("rejects unsafe FTS tokenizers", () => {
    const db = OmgDatabase.memory();
    expect(() => db.createFts5Table("docs", ["key", "content"], "porter'; DROP TABLE docs; --")).toThrow(
      /Invalid FTS5 tokenizer/,
    );
    db.close();
  });

  test("transaction rolls back on thrown error", () => {
    const db = OmgDatabase.memory();
    db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)");
    expect(() =>
      db.transaction(() => {
        db.run("INSERT INTO t VALUES (?, ?)", [1, "a"]);
        throw new Error("forced rollback");
      }),
    ).toThrow();

    const rows = db.all("SELECT * FROM t");
    expect(rows).toHaveLength(0);
    db.close();
  });

  test("migrations apply once", () => {
    const db = OmgDatabase.memory();
    const migrations: Migration[] = [
      { id: "001-create", sql: "CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)" },
      { id: "002-seed", sql: "INSERT INTO items (val) VALUES ('a')" },
    ];

    db.migrate(migrations);
    db.migrate(migrations);

    const rows = db.all<{ c: number }>("SELECT COUNT(*) AS c FROM items");
    expect(rows[0]?.c).toBe(1);
    expect(db.getAppliedMigrations()).toEqual(["001-create", "002-seed"]);
    db.close();
  });

  test("file-backed open defaults to WAL", () => {
    const dbPath = join(tmpdir(), `omg-state-db-${Date.now()}.sqlite3`);
    cleanupPaths.push(dbPath, `${dbPath}-shm`, `${dbPath}-wal`);
    const db = OmgDatabase.open(dbPath);
    expect(db.getJournalMode().toLowerCase()).toBe("wal");
    db.close();
  });
});
