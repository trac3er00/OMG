"""SemanticMemory — full-text search with smart scoring and entity links.

Stores general facts and relationships with scored retrieval combining
BM25 relevance, importance, recency, and access frequency. Entity links
track directional relationships between named entities in a separate table.

Design decisions:
- Scoring weights: BM25 (40%) + importance (30%) + recency (20%) + access_freq (10%)
- BM25 normalization inverts negative FTS5 scores to 0.0-1.0 range
- Recency decays linearly over 7 days then clamps to 0.0
- Consolidation uses word-level Jaccard similarity via FTS5-indexed content
- Links table co-located in same SQLite DB with CREATE IF NOT EXISTS per connection
"""
from __future__ import annotations

import sqlite3
import time
from importlib import import_module
from typing import cast

from claude_experimental.memory.store import MemoryStore

# Recency decay window: facts older than this get recency=0.0
_RECENCY_WINDOW_SECONDS = 7 * 24 * 3600  # 7 days


class SemanticMemory:
    """Stores general facts and relationships with full-text search and smart scoring.

    Scoring formula for search results:
        final_score = bm25_norm * 0.4 + importance * 0.3 + recency * 0.2 + frequency * 0.1

    Entity links are stored in a ``semantic_links`` table in the same SQLite DB.
    """

    def __init__(self, store: MemoryStore | None = None):
        self.store: MemoryStore = store or MemoryStore()
        self._init_links_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _LINKS_DDL: str = """\
CREATE TABLE IF NOT EXISTS semantic_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_links_from ON semantic_links(from_entity);
CREATE INDEX IF NOT EXISTS idx_semantic_links_to ON semantic_links(to_entity);
"""

    def _init_links_table(self) -> None:
        """Create the semantic_links table if it does not exist."""
        conn = self.store.connect()
        try:
            _ = conn.executescript(self._LINKS_DDL)
        finally:
            conn.close()

    def _connect_with_links(self) -> sqlite3.Connection:
        """Open a connection and ensure the semantic_links table is present.

        Needed because :memory: databases lose tables between connections.
        """
        conn = self.store.connect()
        _ = conn.executescript(self._LINKS_DDL)
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_fact(
        self,
        content: str,
        entity: str | None = None,
        importance: float = 0.5,
        scope: str = "project",
        metadata: dict[str, object] | None = None,
    ) -> int:
        """Store a semantic fact with optional entity tagging.

        Args:
            content: The fact text to store.
            entity: Optional entity name this fact relates to.
            importance: Importance weight 0.0-1.0 (default 0.5).
            scope: Storage scope — ``'project'`` or ``'user'``.
            metadata: Optional additional metadata dict.

        Returns:
            The memory ID of the stored fact.
        """
        _require_memory_enabled()

        store_metadata: dict[str, object] = {}
        if entity is not None:
            store_metadata["entity"] = entity
        if metadata:
            store_metadata.update(metadata)

        return self.store.save(
            content=content,
            memory_type="semantic",
            importance=importance,
            scope=scope,
            metadata=store_metadata,
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.0,
    ) -> list[dict[str, object]]:
        """Search stored facts using full-text search with smart scoring.

        Combines four signals into a final score (0.0-1.0):
            - **BM25 relevance (40%)**: Text match quality from FTS5.
            - **Importance (30%)**: Stored importance weight.
            - **Recency (20%)**: Linear decay over 7 days.
            - **Access frequency (10%)**: Normalized by max access count.

        Args:
            query: Full-text search query string.
            limit: Maximum number of results (default 5).
            min_score: Minimum combined score threshold (default 0.0).

        Returns:
            List of dicts sorted by score descending.  Each dict contains
            ``id``, ``content``, ``memory_type``, ``importance``, ``scope``,
            ``metadata``, ``created_at``, ``accessed_at``, ``access_count``,
            and ``score``.
        """
        _require_memory_enabled()

        conn = self.store.connect()
        try:
            sql = """
                SELECT m.id, m.content, m.memory_type, m.importance, m.scope,
                       m.metadata, m.created_at, m.accessed_at, m.access_count,
                       bm25(memories_fts) AS bm25_raw
                FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ?
                  AND m.memory_type = 'semantic'
                ORDER BY bm25(memories_fts)
            """
            rows = cast(list[sqlite3.Row], conn.execute(sql, (query,)).fetchall())

            if not rows:
                return []

            now = time.time()

            # --- Normalize BM25 ---
            # bm25() returns negative values; more negative = better match.
            bm25_values = [float(cast(float, r["bm25_raw"])) for r in rows]
            bm25_best = min(bm25_values)
            bm25_worst = max(bm25_values)
            bm25_range = bm25_worst - bm25_best if bm25_worst != bm25_best else 1.0

            # --- Normalize access frequency ---
            max_access = max(int(cast(int, r["access_count"])) for r in rows)
            max_access = max(max_access, 1)

            scored: list[dict[str, object]] = []
            for row in rows:
                memory = dict(row)

                # BM25 component (invert: higher = better match)
                raw_bm25 = float(cast(float, memory.pop("bm25_raw")))
                bm25_norm = (bm25_worst - raw_bm25) / bm25_range

                # Importance component (already 0.0-1.0)
                importance = float(cast(float, memory["importance"]))

                # Recency component (linear decay over 7 days)
                created = float(cast(float, memory["created_at"]))
                age = max(0.0, now - created)
                recency = max(0.0, 1.0 - age / _RECENCY_WINDOW_SECONDS)

                # Access frequency component
                access_count = int(cast(int, memory["access_count"]))
                frequency = access_count / max_access

                final = (
                    bm25_norm * 0.4
                    + importance * 0.3
                    + recency * 0.2
                    + frequency * 0.1
                )

                if final >= min_score:
                    memory["score"] = round(final, 6)
                    scored.append(memory)

            scored.sort(key=lambda r: float(cast(float, r["score"])), reverse=True)
            top = scored[:limit]

            # Bump access metadata for returned results
            if top:
                ids = [cast(int, r["id"]) for r in top]
                placeholders = ",".join("?" * len(ids))
                _ = conn.execute(
                    "UPDATE memories SET access_count = access_count + 1, accessed_at = ? WHERE id IN (%s)" % placeholders,
                    [now, *ids],
                )
                conn.commit()

            return top
        except sqlite3.OperationalError:
            # FTS table empty or malformed query
            return []
        finally:
            conn.close()

    def add_link(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
    ) -> int:
        """Create a directional link between two entities.

        Args:
            from_entity: Source entity name.
            to_entity: Target entity name.
            relationship_type: Type of relationship (e.g. ``'used_by'``).

        Returns:
            The link ID.
        """
        _require_memory_enabled()

        conn = self._connect_with_links()
        try:
            created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            cursor = conn.execute(
                """
                INSERT INTO semantic_links
                    (from_entity, to_entity, relationship_type, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (from_entity, to_entity, relationship_type, created_at),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_links(self, entity: str) -> list[dict[str, object]]:
        """Get all links involving an entity (as source or target).

        Args:
            entity: Entity name to look up.

        Returns:
            List of dicts with ``id``, ``from_entity``, ``to_entity``,
            ``relationship_type``, and ``created_at``.
        """
        _require_memory_enabled()

        conn = self._connect_with_links()
        try:
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    """
                    SELECT id, from_entity, to_entity, relationship_type, created_at
                    FROM semantic_links
                    WHERE from_entity = ? OR to_entity = ?
                    ORDER BY created_at DESC
                    """,
                    (entity, entity),
                ).fetchall(),
            )
            return [cast(dict[str, object], dict(r)) for r in rows]
        finally:
            conn.close()

    def consolidate(self, threshold: float = 0.8) -> int:
        """Merge similar semantic entries that share high content overlap.

        For each pair of semantic memories, computes word-level Jaccard
        similarity.  When similarity exceeds *threshold*, the lower-importance
        entry is deleted and its access count is folded into the survivor.

        Args:
            threshold: Minimum Jaccard similarity for merging (default 0.8).

        Returns:
            Number of entries removed by merging.
        """
        _require_memory_enabled()

        conn = self.store.connect()
        try:
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    """
                    SELECT id, content, importance, access_count
                    FROM memories WHERE memory_type = 'semantic'
                    ORDER BY importance DESC
                    """
                ).fetchall(),
            )

            if len(rows) < 2:
                return 0

            merged_ids: set[int] = set()

            for i, primary in enumerate(rows):
                primary_id = int(cast(int, primary["id"]))
                if primary_id in merged_ids:
                    continue

                primary_words = set(str(cast(str, primary["content"])).lower().split())
                if not primary_words:
                    continue

                for j in range(i + 1, len(rows)):
                    secondary = rows[j]
                    secondary_id = int(cast(int, secondary["id"]))
                    if secondary_id in merged_ids:
                        continue

                    secondary_words = set(
                        str(cast(str, secondary["content"])).lower().split()
                    )
                    if not secondary_words:
                        continue

                    # Jaccard similarity
                    intersection = len(primary_words & secondary_words)
                    union = len(primary_words | secondary_words)
                    similarity = intersection / union if union > 0 else 0.0

                    if similarity >= threshold:
                        # Fold secondary access_count into primary, delete secondary
                        sec_access = int(cast(int, secondary["access_count"]))
                        _ = conn.execute(
                            "UPDATE memories SET access_count = access_count + ? WHERE id = ?",
                            (sec_access, primary_id),
                        )
                        _ = conn.execute(
                            "DELETE FROM memories WHERE id = ?", (secondary_id,)
                        )
                        merged_ids.add(secondary_id)

            if merged_ids:
                conn.commit()

            return len(merged_ids)
        finally:
            conn.close()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _require_memory_enabled() -> None:
    """Check that the experimental memory feature flag is enabled."""
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")
