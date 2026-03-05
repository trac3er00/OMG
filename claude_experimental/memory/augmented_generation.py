from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from importlib import import_module
from typing import cast

from claude_experimental.memory.api import recall
from claude_experimental.memory.store import MemoryStore


class MemoryAugmenter:
    def __init__(self, db_path: str | None = None):
        try:
            _require_memory_enabled()
        except RuntimeError:
            pass
        self._store: MemoryStore = MemoryStore(db_path=db_path, scope="project")

    def augment_prompt(
        self,
        base_prompt: str,
        context_scope: str = "project",
        max_memories: int = 5,
    ) -> str:
        try:
            _require_memory_enabled()
        except RuntimeError:
            return base_prompt

        try:
            safe_limit = max(0, int(max_memories))
            if safe_limit == 0:
                return base_prompt

            memories = recall(
                base_prompt,
                limit=safe_limit,
                scope_filter=context_scope,
            )
            if not memories:
                return base_prompt

            lines = [
                "## Relevant Context from Memory",
                "",
            ]
            for idx, memory in enumerate(memories[:safe_limit], start=1):
                lines.append(
                    f"{idx}. {memory.content} (relevance: {memory.relevance_score:.2f}, type: {memory.source_type})"
                )

            lines.extend(["", "---", "", base_prompt])
            return "\n".join(lines)
        except Exception:
            return base_prompt

    def record_outcome(self, prompt_hash: str, success: bool, memory_ids_used: Iterable[int]) -> None:
        _require_memory_enabled()

        memory_ids = sorted({int(memory_id) for memory_id in memory_ids_used})
        if not memory_ids:
            return

        conn = self._store.connect()
        try:
            self._ensure_outcome_table(conn)
            now = time.time()
            _ = conn.executemany(
                """
                INSERT INTO augmentation_outcomes (memory_id, prompt_hash, success, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(memory_id, prompt_hash, 1 if success else 0, now) for memory_id in memory_ids],
            )
            conn.commit()
        finally:
            conn.close()

    def get_contribution_stats(self) -> dict[int, float]:
        _require_memory_enabled()

        conn = self._store.connect()
        try:
            self._ensure_outcome_table(conn)
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                """
                SELECT memory_id, AVG(success) AS success_rate
                FROM augmentation_outcomes
                GROUP BY memory_id
                ORDER BY memory_id ASC
                """
                ).fetchall(),
            )
            return {
                int(cast(int | float | str, row[0])): float(cast(int | float | str, row[1]))
                for row in rows
                if row[0] is not None and row[1] is not None
            }
        finally:
            conn.close()

    def _ensure_outcome_table(self, conn: sqlite3.Connection) -> None:
        _ = conn.execute(
            """
            CREATE TABLE IF NOT EXISTS augmentation_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                prompt_hash TEXT NOT NULL,
                success INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        _ = conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_augmentation_outcomes_memory_id
            ON augmentation_outcomes(memory_id)
            """
        )
        _ = conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_augmentation_outcomes_prompt_hash
            ON augmentation_outcomes(prompt_hash)
            """
        )
        conn.commit()


__all__ = ["MemoryAugmenter"]


def _require_memory_enabled() -> None:
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")
