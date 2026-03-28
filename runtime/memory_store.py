"""Encrypted runtime memory store for scoped OMG state and artifacts.

This module provides a dual-backend (SQLite or JSON) memory layer used by OMG
runtime components to persist run/profile-scoped notes, searchable memory
entries, and artifact handles. Stored content is PII-redacted on write and can
be encrypted at rest using Fernet (or deterministic fallback encryption).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import base64
import hashlib
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime.profile_io import classify_preference_section, is_destructive_preference

try:
    from cryptography.fernet import Fernet, InvalidToken

    _has_fernet = True
except ModuleNotFoundError:
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]
    _has_fernet = False


class MemoryStoreFullError(Exception):
    """Raised when the memory store reaches configured capacity."""

    pass


_MAX_ITEMS = 10_000
_PREFERENCE_SIGNAL_LIMIT = 12
_PREFERENCE_VALUE_MAX = 160
_PREFERENCE_ALLOWED_FIELDS = (
    "preferences.architecture_requests",
    "preferences.constraints.",
    "user_vector.tags",
)
_INLINE_METADATA_MAX = 512
_DEFAULT_NAMESPACE = "default"
_DEFAULT_MEMORY_HOST = "127.0.0.1"
_ENCRYPTED_PREFIX = "enc:v1:"
_JSON_ENVELOPE_FORMAT = "omg.memory.json.v1"
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED:EMAIL]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[REDACTED:PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED:SSN]"),
)
_Item = dict[str, Any]  # pyright: ignore[reportExplicitAny]


class MemoryStore:
    """Persist, query, and index encrypted runtime memory entries.

    The store supports both JSON and SQLite backends, optional full-text search,
    run/profile namespace scoping, retention windows, artifact indexing, and
    quarantine promotion flows.
    """

    def __init__(self, store_path: str | None = None) -> None:
        """Initialize a memory store bound to a JSON or SQLite path.

        Args:
            store_path: Optional explicit storage path. Defaults to the shared
                OMG SQLite memory path under the user's home directory.
        """
        if store_path is None:
            store_path = str(Path.home() / ".omg" / "shared-memory" / "store.sqlite3")
        self._memory_host = (os.environ.get("OMG_MEMORY_HOST", _DEFAULT_MEMORY_HOST).strip() or _DEFAULT_MEMORY_HOST)
        self._conn: sqlite3.Connection | None = None
        self._fts_enabled = False
        self._items: list[_Item] = []
        self._store_path = ""
        self._backend = "json"

        self.store_path = store_path

    @property
    def store_path(self) -> str:
        """Return the currently configured store path."""
        return self._store_path

    @store_path.setter
    def store_path(self, store_path: str) -> None:
        """Switch store path and reinitialize backend-specific state.

        Args:
            store_path: New memory store path.
        """
        normalized_path = str(store_path)
        if normalized_path == self._store_path:
            return

        self.close()
        self._store_path = normalized_path
        self._backend = "json" if Path(normalized_path).suffix.lower() == ".json" else "sqlite"
        self._items = []
        self._fts_enabled = False

        if self._backend == "json":
            self._items = self._load_json_items()
        else:
            self._init_sqlite()

    def close(self) -> None:
        """Close the active SQLite connection if one is open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            return

    def add(
        self,
        key: str,
        content: str,
        source_cli: str,
        tags: list[str] | None = None,
        *,
        run_id: str = "",
        profile_id: str = "",
        namespace: str = _DEFAULT_NAMESPACE,
        retention_days: int | None = None,
    ) -> _Item:
        """Insert a memory item after redaction, scoping, and retention mapping.

        Args:
            key: Logical memory key.
            content: Memory content to persist.
            source_cli: Source runtime/CLI identifier.
            tags: Optional list of tags.
            run_id: Optional run scope identifier.
            profile_id: Optional profile scope identifier.
            namespace: Namespace token for multi-host isolation.
            retention_days: Optional retention period used to compute expiry.

        Returns:
            Persisted memory item payload.

        Raises:
            MemoryStoreFullError: If max item capacity has been reached.
        """
        if self.count() >= _MAX_ITEMS:
            raise MemoryStoreFullError(
                f"Memory store is full ({_MAX_ITEMS} items). "
                "Delete items before adding new ones."
            )

        now = _utc_now_iso()
        canonical_namespace = _qualify_namespace(namespace)
        canonical_retention_days = _normalize_retention_days(retention_days)
        expires_at = _compute_expires_at(now, canonical_retention_days)
        redacted_content = _redact_pii(content)
        item: _Item = {
            "id": str(uuid.uuid4()),
            "key": key,
            "content": redacted_content,
            "source_cli": source_cli,
            "tags": tags if tags is not None else [],
            "run_id": run_id,
            "profile_id": profile_id,
            "namespace": canonical_namespace,
            "retention_days": canonical_retention_days,
            "expires_at": expires_at,
            "created_at": now,
            "updated_at": now,
            "quarantined": False,
        }
        if self._backend == "json":
            self._items.append(item)
            self._save_json_items()
            return item

        conn = self._sqlite_conn()
        conn.execute(
            """
            INSERT INTO memories(
                id, key, content, source_cli, tags_json, run_id, profile_id,
                namespace, retention_days, expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["key"],
                self._encrypt_text(item["content"], purpose="sqlite-content"),
                item["source_cli"],
                json.dumps(item["tags"], ensure_ascii=True),
                run_id,
                profile_id,
                canonical_namespace,
                canonical_retention_days,
                expires_at,
                now,
                now,
            ),
        )
        self._upsert_fts(item)
        conn.commit()
        return item

    def get(self, item_id: str) -> _Item | None:
        """Fetch a memory item by identifier.

        Args:
            item_id: Item UUID.

        Returns:
            Matching memory item, or ``None`` when missing.
        """
        if self._backend == "json":
            for item in self._items:
                if item["id"] == item_id:
                    return item
            return None

        row = self._sqlite_conn().execute(
            "SELECT * FROM memories WHERE id = ?",
            (item_id,),
        ).fetchone()
        return self._row_to_item(row) if row is not None else None

    def update(
        self,
        item_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> _Item | None:
        """Update mutable fields of an existing memory item.

        Args:
            item_id: Identifier of the item to update.
            content: Optional replacement content.
            tags: Optional replacement tags.

        Returns:
            Updated item payload, or ``None`` if the item does not exist.
        """
        if self._backend == "json":
            item = self.get(item_id)
            if item is None:
                return None

            if content is not None:
                item["content"] = content
            if tags is not None:
                item["tags"] = tags
            item["updated_at"] = _utc_now_iso()
            self._save_json_items()
            return item

        item = self.get(item_id)
        if item is None:
            return None
        new_content = content if content is not None else str(item.get("content", ""))
        new_tags = tags if tags is not None else item.get("tags", [])
        updated_at = _utc_now_iso()
        self._sqlite_conn().execute(
            "UPDATE memories SET content = ?, tags_json = ?, updated_at = ? WHERE id = ?",
            (self._encrypt_text(new_content, purpose="sqlite-content"), json.dumps(new_tags, ensure_ascii=True), updated_at, item_id),
        )
        updated = {
            **item,
            "content": new_content,
            "tags": new_tags,
            "updated_at": updated_at,
        }
        self._upsert_fts(updated)
        self._sqlite_conn().commit()
        return updated

    def delete(self, item_id: str) -> bool:
        """Delete a memory item by identifier.

        Args:
            item_id: Identifier of the item to delete.

        Returns:
            ``True`` when an item was removed, otherwise ``False``.
        """
        if self._backend == "json":
            for idx, item in enumerate(self._items):
                if item["id"] == item_id:
                    del self._items[idx]
                    self._save_json_items()
                    return True
            return False

        cur = self._sqlite_conn().execute("DELETE FROM memories WHERE id = ?", (item_id,))
        self._delete_fts(item_id)
        self._sqlite_conn().commit()
        return cur.rowcount > 0

    def search(
        self,
        query: str,
        source_cli: str | None = None,
        *,
        namespace: str | None = None,
        include_quarantined: bool = False,
    ) -> list[_Item]:
        """Run substring search across key/content/tags with scope filters.

        Args:
            query: Case-insensitive search query.
            source_cli: Optional source filter.
            namespace: Optional namespace filter.
            include_quarantined: Whether quarantined items are searchable.

        Returns:
            Matching memory items.
        """
        if self._backend == "json":
            q = query.lower()
            results: list[_Item] = []
            canonical_namespace = _qualify_namespace(namespace) if namespace is not None else None
            for item in self._items:
                normalized_item = _normalize_item(item)
                if _is_expired(normalized_item):
                    continue
                if source_cli is not None and item["source_cli"] != source_cli:
                    continue
                if canonical_namespace is not None and normalized_item.get("namespace") != canonical_namespace:
                    continue
                if not include_quarantined and bool(normalized_item.get("quarantined", False)):
                    continue
                key_str = str(item.get("key", "")).lower()
                content_str = str(item.get("content", "")).lower()
                tags_raw = item.get("tags", [])
                tags_str = " ".join(str(t).lower() for t in tags_raw) if isinstance(tags_raw, list) else ""
                if q in key_str or q in content_str or q in tags_str:
                    results.append(normalized_item)
            return results

        rows = self.list_all(
            source_cli=source_cli,
            namespace=namespace,
            include_quarantined=include_quarantined,
        )
        q = query.lower()
        matches: list[_Item] = []
        for item in rows:
            key_str = str(item.get("key", "")).lower()
            content_str = str(item.get("content", "")).lower()
            tags_raw = item.get("tags", [])
            tags_str = " ".join(str(t).lower() for t in tags_raw) if isinstance(tags_raw, list) else ""
            if q in key_str or q in content_str or q in tags_str:
                matches.append(item)
        return matches

    def list_all(
        self,
        source_cli: str | None = None,
        *,
        run_id: str | None = None,
        profile_id: str | None = None,
        namespace: str | None = None,
        include_quarantined: bool = False,
    ) -> list[_Item]:
        """List all non-expired items with optional scope filters.

        Args:
            source_cli: Optional source filter.
            run_id: Optional run scope filter.
            profile_id: Optional profile scope filter.
            namespace: Optional namespace filter.
            include_quarantined: Whether quarantined items are included.

        Returns:
            Filtered list of memory items ordered by recency for SQLite.
        """
        if self._backend == "json":
            out = [_normalize_item(item) for item in self._items if not _is_expired(item)]
            if source_cli is not None:
                out = [i for i in out if i.get("source_cli") == source_cli]
            if run_id is not None:
                out = [i for i in out if str(i.get("run_id", "")) == run_id]
            if profile_id is not None:
                out = [i for i in out if str(i.get("profile_id", "")) == profile_id]
            if namespace is not None:
                canonical_namespace = _qualify_namespace(namespace)
                out = [i for i in out if str(i.get("namespace", "")) == canonical_namespace]
            if not include_quarantined:
                out = [i for i in out if not bool(i.get("quarantined", False))]
            return out

        where: list[str] = []
        params: list[Any] = []
        if source_cli is not None:
            where.append("source_cli = ?")
            params.append(source_cli)
        if run_id is not None:
            where.append("run_id = ?")
            params.append(run_id)
        if profile_id is not None:
            where.append("profile_id = ?")
            params.append(profile_id)
        if namespace is not None:
            where.append("namespace = ?")
            params.append(_qualify_namespace(namespace))
        if not include_quarantined:
            where.append("quarantined = 0")
        where.append("(expires_at IS NULL OR expires_at = '' OR expires_at > ?)")
        params.append(_utc_now_iso())

        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC"
        rows = self._sqlite_conn().execute(sql, tuple(params)).fetchall()
        return [self._row_to_item(row) for row in rows]

    def export_all(self, *, include_quarantined: bool = False) -> list[_Item]:
        """Export all stored items for backup or transfer.

        Args:
            include_quarantined: Whether to include quarantined entries.

        Returns:
            Serialized list of memory items.
        """
        return self.list_all(include_quarantined=include_quarantined)

    def import_items(self, items: list[_Item], *, quarantined: bool = False) -> int:
        """Import external memory items, skipping duplicate identifiers.

        Args:
            items: Items to import.
            quarantined: Whether imported records should be quarantined.

        Returns:
            Number of items inserted.
        """
        if self._backend == "json":
            existing_ids = {str(i["id"]) for i in self._items}
            added = 0
            for item in items:
                item_id = str(item.get("id", ""))
                if item_id and item_id not in existing_ids:
                    normalized = _normalize_item(item)
                    normalized["quarantined"] = bool(quarantined)
                    self._items.append(normalized)
                    existing_ids.add(item_id)
                    added += 1
            if added:
                self._save_json_items()
            return added

        conn = self._sqlite_conn()
        added = 0
        for item in items:
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                continue
            existing = conn.execute("SELECT 1 FROM memories WHERE id = ?", (item_id,)).fetchone()
            if existing is not None:
                continue
            key = str(item.get("key", ""))
            content = str(item.get("content", ""))
            source_cli = str(item.get("source_cli", ""))
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            created_at = str(item.get("created_at", "")) or _utc_now_iso()
            updated_at = str(item.get("updated_at", "")) or created_at
            namespace = _qualify_namespace(item.get("namespace", _DEFAULT_NAMESPACE))
            retention_days = _normalize_retention_days(item.get("retention_days"))
            expires_at = str(item.get("expires_at", "")).strip() or _compute_expires_at(created_at, retention_days)
            redacted_content = _redact_pii(content)
            run_id = str(item.get("run_id", ""))
            profile_id = str(item.get("profile_id", ""))
            quarantined_flag = bool(quarantined)
            conn.execute(
                """
                INSERT INTO memories(
                    id, key, content, source_cli, tags_json, run_id, profile_id,
                    namespace, retention_days, expires_at, created_at, updated_at, quarantined
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    key,
                    self._encrypt_text(redacted_content, purpose="sqlite-content"),
                    source_cli,
                    json.dumps(tags, ensure_ascii=True),
                    run_id,
                    profile_id,
                    namespace,
                    retention_days,
                    expires_at,
                    created_at,
                    updated_at,
                    1 if quarantined_flag else 0,
                ),
            )
            self._upsert_fts(
                {
                    "id": item_id,
                    "key": key,
                    "content": redacted_content,
                    "tags": tags,
                }
            )
            added += 1
        if added:
            conn.commit()
        return added

    def count(self) -> int:
        """Return the number of stored memory items."""
        if self._backend == "json":
            return len(self._items)
        row = self._sqlite_conn().execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        if row is None:
            return 0
        return int(row["n"])

    def clear(self) -> int:
        """Delete all memories and related artifact/lineage records.

        Returns:
            Number of memory items that existed before clearing.
        """
        n = self.count()
        if self._backend == "json":
            self._items.clear()
            self._save_json_items()
            return n

        conn = self._sqlite_conn()
        conn.execute("DELETE FROM memories")
        conn.execute("DELETE FROM artifacts")
        conn.execute("DELETE FROM lineage_edges")
        if self._fts_enabled:
            conn.execute("DELETE FROM memories_fts")
        conn.commit()
        return n

    def promote_item(self, item_id: str) -> bool:
        """Promote a quarantined item back into normal visibility.

        Args:
            item_id: Identifier of the item to promote.

        Returns:
            ``True`` when the item exists (and is promoted if quarantined).
        """
        if self._backend == "json":
            item = self.get(item_id)
            if item is None:
                return False
            if bool(item.get("quarantined", False)):
                item["quarantined"] = False
                item["updated_at"] = _utc_now_iso()
                self._save_json_items()
            return True

        cur = self._sqlite_conn().execute(
            "UPDATE memories SET quarantined = 0, updated_at = ? WHERE id = ?",
            (_utc_now_iso(), item_id),
        )
        self._sqlite_conn().commit()
        return cur.rowcount > 0

    def query_scoped(
        self,
        query: str,
        *,
        run_id: str,
        profile_id: str,
        limit: int = 20,
    ) -> list[_Item]:
        """Query memory limited to a specific run/profile scope.

        Args:
            query: Search query.
            run_id: Required run scope.
            profile_id: Required profile scope.
            limit: Maximum number of returned rows.

        Returns:
            Matching scoped memory items.
        """
        bounded_limit = max(1, min(int(limit), 200))
        if self._backend == "json":
            rows = self.search(query)
            scoped = [
                row
                for row in rows
                if str(row.get("run_id", "")) == run_id
                and str(row.get("profile_id", "")) == profile_id
            ]
            return scoped[:bounded_limit]

        q = f"%{query.lower()}%"
        rows = self._sqlite_conn().execute(
            """
            SELECT * FROM memories
            WHERE run_id = ?
              AND profile_id = ?
              AND quarantined = 0
              AND (lower(key) LIKE ? OR lower(content) LIKE ? OR lower(tags_json) LIKE ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (run_id, profile_id, q, q, q, bounded_limit),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def hybrid_retrieve(
        self,
        query: str,
        *,
        run_id: str,
        profile_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve scoped memories ranked by FTS and token-overlap scoring.

        Args:
            query: Search query.
            run_id: Required run scope.
            profile_id: Required profile scope.
            limit: Maximum number of scored results.

        Returns:
            Ranked memory rows with a ``score`` field.
        """
        bounded_limit = max(1, min(int(limit), 100))
        if self._backend == "json":
            rows = self.query_scoped(query, run_id=run_id, profile_id=profile_id, limit=bounded_limit)
            return [
                {
                    **row,
                    "score": float(_token_overlap_score(query, row)),
                }
                for row in rows
            ]

        candidates: list[tuple[_Item, float]] = []
        conn = self._sqlite_conn()
        if self._fts_enabled:
            rows = conn.execute(
                """
                SELECT m.*, bm25(memories_fts) AS rank
                FROM memories_fts
                JOIN memories AS m ON m.id = memories_fts.id
                WHERE memories_fts MATCH ?
                  AND m.run_id = ?
                  AND m.profile_id = ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (_fts_query(query), run_id, profile_id, bounded_limit),
            ).fetchall()
            for row in rows:
                item = self._row_to_item(row)
                rank = row["rank"] if isinstance(row["rank"], (int, float)) else 0.0
                keyword_score = 1.0 / (1.0 + max(float(rank), 0.0))
                semantic_score = _token_overlap_score(query, item)
                candidates.append((item, (0.7 * keyword_score) + (0.3 * semantic_score)))

        if not candidates:
            for item in self.query_scoped(query, run_id=run_id, profile_id=profile_id, limit=bounded_limit):
                candidates.append((item, _token_overlap_score(query, item)))

        candidates.sort(key=lambda pair: pair[1], reverse=True)
        return [{**item, "score": round(score, 6)} for item, score in candidates[:bounded_limit]]

    def index_artifact(
        self,
        *,
        run_id: str,
        profile_id: str,
        kind: str,
        path: str,
        summary: str,
        size_bytes: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Index an artifact handle associated with a run/profile scope.

        Args:
            run_id: Run identifier owning the artifact.
            profile_id: Profile identifier owning the artifact.
            kind: Artifact kind token.
            path: Artifact filesystem path.
            summary: Bounded artifact summary text.
            size_bytes: Artifact size in bytes.
            metadata: Optional metadata map (sanitized before persistence).

        Returns:
            Normalized artifact handle payload.
        """
        now = _utc_now_iso()
        artifact_id = f"artifact-{uuid.uuid4().hex}"
        clean_metadata = _sanitize_metadata(metadata or {})
        handle = {
            "artifact_id": artifact_id,
            "run_id": run_id,
            "profile_id": profile_id,
            "kind": kind,
            "path": path,
            "summary": summary,
            "size_bytes": int(size_bytes),
            "metadata": clean_metadata,
            "created_at": now,
        }

        if self._backend == "json":
            payload = {
                "field": "artifact.handle",
                "value": json.dumps(handle, ensure_ascii=True),
                "source": "artifact_index",
                "project_scope": "",
                "run_id": run_id,
                "profile_id": profile_id,
                "updated_at": now,
            }
            self.add(
                key=f"artifact:{artifact_id}",
                content=json.dumps(payload, ensure_ascii=True),
                source_cli="runtime",
                tags=[f"artifact_kind:{kind}"],
                run_id=run_id,
                profile_id=profile_id,
            )
            return handle

        self._sqlite_conn().execute(
            """
            INSERT INTO artifacts(
                artifact_id, run_id, profile_id, kind, path, summary, size_bytes, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                run_id,
                profile_id,
                kind,
                path,
                summary,
                int(size_bytes),
                json.dumps(clean_metadata, ensure_ascii=True),
                now,
            ),
        )
        self._sqlite_conn().commit()
        return handle

    def query_artifacts(
        self,
        *,
        run_id: str,
        profile_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query artifact handles by run/profile/kind scope.

        Args:
            run_id: Run identifier to query.
            profile_id: Optional profile filter.
            kind: Optional artifact kind filter.
            limit: Maximum number of returned handles.

        Returns:
            Artifact handle payloads with sanitized metadata.
        """
        bounded_limit = max(1, min(int(limit), 200))
        if self._backend == "json":
            handles: list[dict[str, Any]] = []
            for item in self.list_all(run_id=run_id, profile_id=profile_id):
                key = str(item.get("key", ""))
                if not key.startswith("artifact:"):
                    continue
                try:
                    payload = json.loads(str(item.get("content", "")))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                value_raw = payload.get("value")
                if not isinstance(value_raw, str):
                    continue
                try:
                    handle = json.loads(value_raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(handle, dict):
                    continue
                if profile_id is not None and str(handle.get("profile_id", "")) != profile_id:
                    continue
                if kind is not None and str(handle.get("kind", "")) != kind:
                    continue
                handles.append(_sanitize_artifact_handle(handle))
            return handles[:bounded_limit]

        where = ["run_id = ?"]
        params: list[Any] = [run_id]
        if profile_id is not None:
            where.append("profile_id = ?")
            params.append(profile_id)
        if kind is not None:
            where.append("kind = ?")
            params.append(kind)
        params.append(bounded_limit)
        rows = self._sqlite_conn().execute(
            f"""
            SELECT artifact_id, run_id, profile_id, kind, path, summary, size_bytes, metadata_json, created_at
            FROM artifacts
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        handles: list[dict[str, Any]] = []
        for row in rows:
            metadata = _parse_json_object(row["metadata_json"])
            handles.append(
                {
                    "artifact_id": row["artifact_id"],
                    "run_id": row["run_id"],
                    "profile_id": row["profile_id"],
                    "kind": row["kind"],
                    "path": row["path"],
                    "summary": row["summary"],
                    "size_bytes": int(row["size_bytes"]),
                    "metadata": _sanitize_metadata(metadata),
                    "created_at": row["created_at"],
                }
            )
        return handles

    def _load_json_items(self) -> list[_Item]:
        path = Path(self.store_path)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, list):
                return raw  # type: ignore[return-value]
            if isinstance(raw, dict) and str(raw.get("format", "")) == _JSON_ENVELOPE_FORMAT:
                encrypted_payload = str(raw.get("payload", ""))
                integrity = raw.get("integrity", {})
                expected_sha = ""
                if isinstance(integrity, dict):
                    expected_sha = str(integrity.get("sha256", ""))
                if not encrypted_payload or hashlib.sha256(encrypted_payload.encode("utf-8")).hexdigest() != expected_sha:
                    return []
                decrypted = self._decrypt_text(encrypted_payload, purpose="json-at-rest")
                if not decrypted:
                    return []
                payload = json.loads(decrypted)
                if isinstance(payload, list):
                    return payload  # type: ignore[return-value]
            return []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save_json_items(self) -> None:
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(self._items, indent=2, ensure_ascii=True) + "\n")
        _ = os.replace(tmp_path, path)

    def _sqlite_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLite backend is not initialized")
        return self._conn

    def _init_sqlite(self) -> None:
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                source_cli TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                profile_id TEXT NOT NULL DEFAULT '',
                namespace TEXT NOT NULL DEFAULT '127.0.0.1:default',
                retention_days INTEGER,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                quarantined INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        _ensure_memory_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(run_id, profile_id, updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                summary TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_scope ON artifacts(run_id, profile_id, created_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lineage_edges (
                edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_node TEXT NOT NULL,
                child_node TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                run_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lineage_scope
            ON lineage_edges(run_id, profile_id, parent_node, child_node)
            """
        )

        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(id UNINDEXED, key, content, tags)
                """
            )
            self._fts_enabled = True
        except sqlite3.OperationalError:
            self._fts_enabled = False

        self._conn = conn
        self._rebuild_fts_if_available()
        conn.commit()

    def _rebuild_fts_if_available(self) -> None:
        if not self._fts_enabled:
            return
        conn = self._sqlite_conn()
        conn.execute("DELETE FROM memories_fts")
        rows = conn.execute("SELECT id, key, content, tags_json FROM memories").fetchall()
        for row in rows:
            tags = _parse_json_array(row["tags_json"])
            conn.execute(
                "INSERT INTO memories_fts(id, key, content, tags) VALUES (?, ?, ?, ?)",
                (row["id"], row["key"], row["content"], " ".join(str(t) for t in tags)),
            )

    def _upsert_fts(self, item: _Item) -> None:
        if not self._fts_enabled:
            return
        conn = self._sqlite_conn()
        conn.execute("DELETE FROM memories_fts WHERE id = ?", (item["id"],))
        tags = item.get("tags", [])
        tags_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
        conn.execute(
            "INSERT INTO memories_fts(id, key, content, tags) VALUES (?, ?, ?, ?)",
            (item["id"], str(item.get("key", "")), str(item.get("content", "")), tags_text),
        )

    def _delete_fts(self, item_id: str) -> None:
        if not self._fts_enabled:
            return
        self._sqlite_conn().execute("DELETE FROM memories_fts WHERE id = ?", (item_id,))

    def _row_to_item(self, row: sqlite3.Row) -> _Item:
        raw_expires_at = row["expires_at"] if "expires_at" in row.keys() else None
        expires_at = _normalize_expires_at(raw_expires_at)
        return {
            "id": row["id"],
            "key": row["key"],
            "content": self._decrypt_text(str(row["content"]), purpose="sqlite-content"),
            "source_cli": row["source_cli"],
            "tags": _parse_json_array(row["tags_json"]),
            "run_id": row["run_id"],
            "profile_id": row["profile_id"],
            "namespace": _qualify_namespace(row["namespace"] if "namespace" in row.keys() else _DEFAULT_NAMESPACE),
            "retention_days": _normalize_retention_days(row["retention_days"] if "retention_days" in row.keys() else None),
            "expires_at": expires_at,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "quarantined": bool(row["quarantined"] if "quarantined" in row.keys() else 0),
        }

    def _derive_key_bytes(self, *, purpose: str) -> bytes:
        secret_seed = os.environ.get("OMG_MEMORY_SECRET", "").strip()
        if not secret_seed:
            secret_seed = f"{os.path.expanduser('~')}|{self._memory_host}|{socket.gethostname()}"
        material = f"{secret_seed}|{self._memory_host}|{purpose}".encode("utf-8")
        return hashlib.sha256(material).digest()

    def _encrypt_text(self, text: str, *, purpose: str) -> str:
        if text.startswith(_ENCRYPTED_PREFIX):
            return text
        key_bytes = self._derive_key_bytes(purpose=purpose)
        if _has_fernet and Fernet is not None:
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            token = Fernet(fernet_key).encrypt(text.encode("utf-8")).decode("utf-8")
            return f"{_ENCRYPTED_PREFIX}{token}"
        encoded = text.encode("utf-8")
        cipher = bytes(byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(encoded))
        return f"{_ENCRYPTED_PREFIX}{base64.urlsafe_b64encode(cipher).decode('ascii')}"

    def _decrypt_text(self, text: str, *, purpose: str) -> str:
        if not text.startswith(_ENCRYPTED_PREFIX):
            return text
        payload = text[len(_ENCRYPTED_PREFIX) :]
        key_bytes = self._derive_key_bytes(purpose=purpose)
        if _has_fernet and Fernet is not None:
            try:
                fernet_key = base64.urlsafe_b64encode(key_bytes)
                return Fernet(fernet_key).decrypt(payload.encode("utf-8")).decode("utf-8")
            except InvalidToken:
                return ""
        try:
            cipher = base64.urlsafe_b64decode(payload.encode("ascii"))
        except ValueError:
            return ""
        plain = bytes(byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(cipher))
        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError:
            return ""


def project_preference_signals(
    project_dir: str,
    *,
    store_path: str | None = None,
    max_signals: int = _PREFERENCE_SIGNAL_LIMIT,
) -> list[dict[str, Any]]:
    """Extract deduplicated project preference signals from memory.

    Args:
        project_dir: Project directory used to match project-scoped signals.
        store_path: Optional explicit memory store path.
        max_signals: Maximum signals to return after deduplication.

    Returns:
        Recent unique preference signals relevant to the project.
    """
    canonical_project = os.path.realpath(project_dir)
    if not canonical_project:
        return []

    limit = max(1, min(int(max_signals), _PREFERENCE_SIGNAL_LIMIT))
    resolved_store_path = store_path
    if resolved_store_path is None:
        legacy_json_path = Path.home() / ".omg" / "shared-memory" / "store.json"
        if legacy_json_path.exists():
            resolved_store_path = str(legacy_json_path)

    store = MemoryStore(store_path=resolved_store_path)
    items = list(reversed(store.list_all()))
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for item in items:
        signal = _extract_project_signal(item, canonical_project)
        if signal is None:
            continue

        signature = (
            str(signal.get("field", "")),
            str(signal.get("value", "")),
            str(signal.get("source", "")),
            str(signal.get("run_id", "")),
        )
        if signature in seen:
            continue
        seen.add(signature)
        results.append(signal)
        if len(results) >= limit:
            break

    return results


def _extract_project_signal(item: _Item, canonical_project: str) -> dict[str, Any] | None:
    raw_content = item.get("content")
    if not isinstance(raw_content, str):
        return None

    try:
        payload = json.loads(raw_content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    scope = _extract_scope(payload, item)
    if os.path.realpath(scope) != canonical_project:
        return None

    field = str(payload.get("field", "")).strip()
    if not _is_allowed_field(field):
        return None

    value = _normalize_value(payload.get("value"))
    if not value:
        return None

    source = str(payload.get("source", "inferred_observation")).strip().lower() or "inferred_observation"
    confidence = _clamp_confidence(payload.get("confidence"))
    contradicted = bool(payload.get("contradicted") is True)

    section = classify_preference_section(field, value)
    destructive = is_destructive_preference(field, value)

    signal: dict[str, Any] = {
        "field": field,
        "value": value,
        "source": source,
        "confidence": confidence,
        "project_scope": canonical_project,
        "run_id": str(payload.get("run_id", "")).strip(),
        "updated_at": str(payload.get("updated_at", item.get("updated_at", ""))).strip(),
        "contradicted": contradicted,
        "section": section,
        "destructive": destructive,
    }
    return signal


def _extract_scope(payload: dict[str, Any], item: _Item) -> str:
    scope = str(payload.get("project_scope", "")).strip()
    if scope:
        return scope
    tags = item.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag)
            if text.startswith("project_scope:"):
                return text.split(":", 1)[1].strip()
    return ""


def _is_allowed_field(field: str) -> bool:
    if field == "preferences.architecture_requests":
        return True
    if field == "user_vector.tags":
        return True
    return field.startswith("preferences.constraints.")


def _normalize_value(raw: Any) -> str:
    text = " ".join(str(raw).strip().split())
    if not text:
        return ""
    return text[:_PREFERENCE_VALUE_MAX]


def _clamp_confidence(raw: Any) -> float:
    try:
        score = float(raw)
    except (TypeError, ValueError):
        score = 0.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return round(score, 3)


def _token_overlap_score(query: str, item: dict[str, Any]) -> float:
    query_tokens = {token for token in query.lower().split() if token}
    if not query_tokens:
        return 0.0
    tags_value = item.get("tags", [])
    tags_text = " ".join(str(tag) for tag in tags_value) if isinstance(tags_value, list) else ""
    corpus = " ".join([str(item.get("key", "")), str(item.get("content", "")), tags_text]).lower()
    corpus_tokens = {token for token in corpus.split() if token}
    if not corpus_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(corpus_tokens))
    return float(overlap) / float(len(query_tokens))


def _fts_query(query: str) -> str:
    tokens = [token for token in query.replace('"', " ").split() if token]
    if not tokens:
        return ""
    return " AND ".join(tokens)


def _parse_json_array(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _parse_json_object(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    omitted_payload = False
    for key, value in metadata.items():
        key_text = str(key)
        if key_text == "payload":
            omitted_payload = True
            continue
        if isinstance(value, str) and len(value) > _INLINE_METADATA_MAX:
            clean[key_text] = value[:_INLINE_METADATA_MAX] + "..."
            continue
        clean[key_text] = value
    if omitted_payload:
        clean["omitted_payload"] = True
    return clean


def _sanitize_artifact_handle(handle: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(handle)
    metadata_raw = sanitized.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    sanitized["metadata"] = _sanitize_metadata(metadata)
    sanitized.pop("payload", None)
    return sanitized


def _normalize_item(item: _Item) -> _Item:
    normalized = dict(item)
    normalized["content"] = _redact_pii(str(item.get("content", "")))
    normalized["namespace"] = _qualify_namespace(item.get("namespace", _DEFAULT_NAMESPACE))
    normalized["retention_days"] = _normalize_retention_days(item.get("retention_days"))
    created_at = str(item.get("created_at", "")).strip() or _utc_now_iso()
    normalized_expires_at = _normalize_expires_at(item.get("expires_at"))
    normalized["expires_at"] = normalized_expires_at or _compute_expires_at(created_at, normalized["retention_days"])
    normalized["quarantined"] = bool(item.get("quarantined", False))
    return normalized


def _redact_pii(content: str) -> str:
    redacted = content
    for pattern, token in _PII_PATTERNS:
        redacted = pattern.sub(token, redacted)
    return redacted


def _qualify_namespace(namespace: object) -> str:
    text = str(namespace or "").strip()
    if not text:
        text = _DEFAULT_NAMESPACE
    if ":" in text:
        host, local = text.split(":", 1)
        if host.strip() and local.strip():
            return f"{host.strip()}:{local.strip()}"
    host = os.environ.get("OMG_MEMORY_HOST", _DEFAULT_MEMORY_HOST).strip() or _DEFAULT_MEMORY_HOST
    return f"{host}:{text}"


def _normalize_retention_days(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    value = int(str(raw).strip())
    if value < 0:
        raise ValueError("retention_days must be >= 0")
    return value


def _compute_expires_at(created_at: str, retention_days: int | None) -> str | None:
    if retention_days is None:
        return None
    try:
        created_dt = datetime.fromisoformat(created_at)
    except ValueError:
        created_dt = datetime.now(timezone.utc)
    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    return (created_dt + timedelta(days=retention_days)).isoformat()


def _is_expired(item: _Item) -> bool:
    expires_at = _normalize_expires_at(item.get("expires_at")) or ""
    if not expires_at:
        return False
    try:
        expires_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    return expires_dt <= datetime.now(timezone.utc)


def _normalize_expires_at(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _ensure_memory_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"]): str(row["name"])
        for row in conn.execute("PRAGMA table_info(memories)").fetchall()
    }
    if "namespace" not in columns:
        _safe_add_memory_column(
            conn,
            "ALTER TABLE memories ADD COLUMN namespace TEXT NOT NULL DEFAULT '127.0.0.1:default'",
        )
    if "retention_days" not in columns:
        _safe_add_memory_column(conn, "ALTER TABLE memories ADD COLUMN retention_days INTEGER")
    if "expires_at" not in columns:
        _safe_add_memory_column(conn, "ALTER TABLE memories ADD COLUMN expires_at TEXT")
    if "quarantined" not in columns:
        _safe_add_memory_column(conn, "ALTER TABLE memories ADD COLUMN quarantined INTEGER NOT NULL DEFAULT 0")


def _safe_add_memory_column(conn: sqlite3.Connection, ddl: str) -> None:
    try:
        conn.execute(ddl)
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["MemoryStore", "MemoryStoreFullError", "project_preference_signals"]
