"""MemoryStore - SQLite-backed storage engine for claude_experimental memory system.

Design decisions:
- WAL mode for concurrent multi-session access
- Connection-per-invocation (hooks are short-lived subprocesses, no pooling)
- FTS5 virtual table for full-text search
- Schema versioning from day one
- Auto-pruning at 10,000 entries per scope
"""
from __future__ import annotations
import os
import sqlite3
import time
import json
from typing import cast

SCHEMA_VERSION = 1
MAX_ENTRIES_PER_SCOPE = 10_000


def _default_db_path(scope: str = "project") -> str:
    """Return default DB path based on scope."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if scope == "user":
        home = os.path.expanduser("~")
        return os.path.join(home, ".omg", "memory.db")
    return os.path.join(project_dir, ".omg", "state", "memory.db")


class MemoryStore:
    """SQLite memory storage with WAL mode, FTS5, and connection-per-invocation pattern.

    Usage:
        with MemoryStore() as store:
            store.save(content="auth bug fixed", memory_type="episodic", importance=0.8)
            results = store.search("auth bug")

    Or without context manager:
        store = MemoryStore()
        conn = store.connect()
        # use conn
        conn.close()
    """

    def __init__(self, db_path: str | None = None, scope: str = "project"):
        self.scope: str = scope
        self.db_path: str = db_path or _default_db_path(scope)
        self._ctx_conn: sqlite3.Connection | None = None
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Open a new connection and initialize the schema if needed."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._init_schema(conn)
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        """Create schema if not exists. Migrate if schema_version < SCHEMA_VERSION."""
        _ = conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'semantic',
                importance REAL NOT NULL DEFAULT 0.5,
                scope TEXT NOT NULL DEFAULT 'session',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                content='memories',
                content_rowid='id'
            );
        """)

        # Set schema version if not present
        row = cast(
            sqlite3.Row | None,
            conn.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone(),
        )
        if row is None:
            _ = conn.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),)
            )
            conn.commit()

        # Triggers to keep FTS in sync with memories table
        _ = conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
            END;
        """)
        conn.commit()

    def pragma(self, pragma_name: str) -> str:
        """Run a PRAGMA and return the string value."""
        conn = self.connect()
        try:
            row = cast(sqlite3.Row | None, conn.execute(f"PRAGMA {pragma_name}").fetchone())
            return str(cast(object, row[0])) if row is not None else ""
        finally:
            conn.close()

    def get_schema_version(self) -> int:
        """Return the schema version stored in the DB."""
        conn = self.connect()
        try:
            row = cast(
                sqlite3.Row | None,
                conn.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone(),
            )
            return int(cast(int | float | str, row[0])) if row is not None else 0
        finally:
            conn.close()

    def save(
        self,
        content: str,
        memory_type: str = "semantic",
        importance: float = 0.5,
        scope: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> int:
        """Save a memory entry. Returns the new row ID."""
        scope = scope or self.scope
        now = time.time()
        conn = self.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO memories (content, memory_type, importance, scope, metadata, created_at, accessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content,
                    memory_type,
                    max(0.0, min(1.0, importance)),  # clamp 0-1
                    scope,
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid
            self._maybe_prune(conn, scope)
            conn.commit()
            return row_id or 0
        finally:
            conn.close()

    def search(
        self,
        query: str,
        limit: int = 10,
        memory_type: str | None = None,
        scope: str | None = None,
        min_importance: float = 0.0,
    ) -> list[dict[str, object]]:
        """Full-text search memories via FTS5. Returns list of memory dicts sorted by relevance."""
        scope = scope or self.scope
        conn = self.connect()
        try:
            # FTS5 search with BM25 ranking
            sql = """
                SELECT m.id, m.content, m.memory_type, m.importance, m.scope,
                       m.metadata, m.created_at, m.accessed_at, m.access_count,
                       m.schema_version,
                       bm25(memories_fts) as fts_score
                FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ?
                  AND m.importance >= ?
            """
            params: list[object] = [query, min_importance]

            if memory_type:
                sql += " AND m.memory_type = ?"
                params.append(memory_type)
            if scope:
                sql += " AND m.scope = ?"
                params.append(scope)

            sql += " ORDER BY fts_score LIMIT ?"
            params.append(limit)

            rows = cast(list[sqlite3.Row], conn.execute(sql, params).fetchall())

            # Update access metadata
            if rows:
                ids = [cast(int, r["id"]) for r in rows]
                _ = conn.execute(
                    f"UPDATE memories SET access_count = access_count + 1, accessed_at = ? WHERE id IN ({','.join('?' * len(ids))})",
                    [time.time()] + ids,
                )
                conn.commit()

            return [cast(dict[str, object], dict(r)) for r in rows]
        except sqlite3.OperationalError:
            # FTS table might be empty or query syntax error
            return []
        finally:
            conn.close()

    def get_by_id(self, memory_id: int) -> dict[str, object] | None:
        """Retrieve a specific memory by ID."""
        conn = self.connect()
        try:
            row = cast(
                sqlite3.Row | None,
                conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone(),
            )
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID."""
        conn = self.connect()
        try:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count(self, scope: str | None = None, memory_type: str | None = None) -> int:
        """Count memories matching optional filters."""
        scope = scope or self.scope
        conn = self.connect()
        try:
            sql = "SELECT COUNT(*) FROM memories WHERE scope = ?"
            params: list[object] = [scope]
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            row = cast(sqlite3.Row | None, conn.execute(sql, params).fetchone())
            return int(cast(int | float | str, row[0])) if row is not None else 0
        finally:
            conn.close()

    def _maybe_prune(self, conn: sqlite3.Connection, scope: str) -> None:
        """Auto-prune if entry count exceeds MAX_ENTRIES_PER_SCOPE for this scope."""
        count_row = cast(
            sqlite3.Row | None,
            conn.execute(
            "SELECT COUNT(*) FROM memories WHERE scope = ?", (scope,)
        ).fetchone(),
        )
        count = int(cast(int | float | str, count_row[0])) if count_row is not None else 0

        if count <= MAX_ENTRIES_PER_SCOPE:
            return

        # Remove lowest-importance entries to bring count back to limit
        excess = count - MAX_ENTRIES_PER_SCOPE
        _ = conn.execute(
            """
            DELETE FROM memories WHERE id IN (
                SELECT id FROM memories WHERE scope = ?
                ORDER BY importance ASC, accessed_at ASC
                LIMIT ?
            )
            """,
            (scope, excess),
        )

    def __enter__(self):
        self._ctx_conn = self.connect()
        return self

    def __exit__(self, *_):
        if self._ctx_conn is not None:
            self._ctx_conn.close()
            self._ctx_conn = None
