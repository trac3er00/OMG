"""SQLite ledger — drop-in replacement for JSONL state files.

Provides the same API as the JSONL tool-ledger and cost-ledger but backed
by SQLite for better query performance and atomic writes.

Migration: reads existing JSONL files on first access and imports them.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator


DB_FILENAME = "omg-ledger.db"


class SQLiteLedger:
    """SQLite-backed ledger for tool usage, costs, and hook errors."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.db_path = os.path.join(project_dir, ".omg", "state", "ledger", DB_FILENAME)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    command TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    exit_code INTEGER DEFAULT 0,
                    session_id TEXT DEFAULT '',
                    extra TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS cost_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    model TEXT DEFAULT '',
                    session_id TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS hook_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    hook TEXT NOT NULL,
                    error TEXT NOT NULL,
                    context TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_tool_ledger_ts ON tool_ledger(ts);
                CREATE INDEX IF NOT EXISTS idx_cost_ledger_ts ON cost_ledger(ts);
                CREATE INDEX IF NOT EXISTS idx_tool_ledger_session ON tool_ledger(session_id);
            """)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Tool Ledger ---

    def append_tool_entry(self, entry: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tool_ledger (ts, tool, command, file_path, exit_code, session_id, extra) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.get("ts", datetime.now(timezone.utc).isoformat()),
                    entry.get("tool", ""),
                    entry.get("command", ""),
                    entry.get("file_path", ""),
                    entry.get("exit_code", 0),
                    entry.get("session_id", ""),
                    json.dumps({k: v for k, v in entry.items()
                                if k not in ("ts", "tool", "command", "file_path", "exit_code", "session_id")}),
                ),
            )

    def get_tool_count(self, since_minutes: int = 60) -> int:
        cutoff = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tool_ledger WHERE ts > datetime('now', ?)",
                (f"-{since_minutes} minutes",),
            ).fetchone()
            return row[0] if row else 0

    def get_recent_tools(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, tool, command, file_path, exit_code, session_id "
                "FROM tool_ledger ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"ts": r[0], "tool": r[1], "command": r[2],
                 "file_path": r[3], "exit_code": r[4], "session_id": r[5]}
                for r in rows
            ]

    # --- Cost Ledger ---

    def append_cost_entry(self, entry: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO cost_ledger (ts, tool, tokens_in, tokens_out, cost_usd, model, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.get("ts", datetime.now(timezone.utc).isoformat()),
                    entry.get("tool", ""),
                    entry.get("tokens_in", 0),
                    entry.get("tokens_out", 0),
                    entry.get("cost_usd", 0.0),
                    entry.get("model", ""),
                    entry.get("session_id", ""),
                ),
            )

    def read_cost_summary(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(tokens_in + tokens_out), SUM(cost_usd) FROM cost_ledger"
            ).fetchone()
            total_entries = row[0] or 0
            total_tokens = row[1] or 0
            total_cost = row[2] or 0.0

            by_tool = {}
            for tool_row in conn.execute(
                "SELECT tool, COUNT(*), SUM(tokens_in + tokens_out), SUM(cost_usd) "
                "FROM cost_ledger GROUP BY tool"
            ).fetchall():
                by_tool[tool_row[0]] = {
                    "count": tool_row[1],
                    "tokens": tool_row[2] or 0,
                    "cost_usd": round(tool_row[3] or 0.0, 6),
                }

            return {
                "entry_count": total_entries,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "by_tool": by_tool,
            }

    # --- Migration ---

    def migrate_from_jsonl(self) -> dict[str, int]:
        """Import existing JSONL ledger files into SQLite."""
        ledger_dir = os.path.dirname(self.db_path)
        imported = {"tool_ledger": 0, "cost_ledger": 0, "hook_errors": 0}

        # Tool ledger
        tool_jsonl = os.path.join(ledger_dir, "tool-ledger.jsonl")
        if os.path.exists(tool_jsonl):
            with open(tool_jsonl, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if isinstance(entry, dict):
                            self.append_tool_entry(entry)
                            imported["tool_ledger"] += 1
                    except (json.JSONDecodeError, TypeError):
                        continue

        # Cost ledger
        cost_jsonl = os.path.join(ledger_dir, "cost-ledger.jsonl")
        if os.path.exists(cost_jsonl):
            with open(cost_jsonl, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if isinstance(entry, dict):
                            self.append_cost_entry(entry)
                            imported["cost_ledger"] += 1
                    except (json.JSONDecodeError, TypeError):
                        continue

        return imported
