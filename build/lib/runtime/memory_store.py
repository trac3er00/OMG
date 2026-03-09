"""MemoryStore — CRUD + JSON persistence for shared memory across CLI providers."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStoreFullError(Exception):
    """Raised when adding to a store that has reached the 10,000 item limit."""


_MAX_ITEMS = 10_000
_PREFERENCE_SIGNAL_LIMIT = 12
_PREFERENCE_VALUE_MAX = 160
_PREFERENCE_ALLOWED_FIELDS = (
    "preferences.architecture_requests",
    "preferences.constraints.",
    "user_vector.tags",
)

# Type alias for memory items — JSON-like dicts.
_Item = dict[str, Any]  # pyright: ignore[reportExplicitAny]


class MemoryStore:
    """Thread-unsafe, file-backed key/content store with JSON persistence.

    Each item follows the schema::

        {
            "id":         str,       # UUID4
            "key":        str,       # user-defined key
            "content":    str,       # the memory text
            "source_cli": str,       # originating CLI name
            "tags":       list[str], # optional tags
            "created_at": str,       # ISO 8601 UTC
            "updated_at": str,       # ISO 8601 UTC
        }

    Persistence uses atomic writes (tmp file + ``os.replace``).
    """

    def __init__(self, store_path: str | None = None) -> None:
        if store_path is None:
            store_path = str(Path.home() / ".omg" / "shared-memory" / "store.json")
        self.store_path: str = store_path
        self._items: list[_Item] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        key: str,
        content: str,
        source_cli: str,
        tags: list[str] | None = None,
    ) -> _Item:
        """Create a new memory item and persist to disk.

        Raises ``MemoryStoreFullError`` when the store already holds
        ``_MAX_ITEMS`` entries.
        """
        if self.count() >= _MAX_ITEMS:
            raise MemoryStoreFullError(
                f"Memory store is full ({_MAX_ITEMS} items). "
                "Delete items before adding new ones."
            )

        now = _utc_now_iso()
        item: _Item = {
            "id": str(uuid.uuid4()),
            "key": key,
            "content": content,
            "source_cli": source_cli,
            "tags": tags if tags is not None else [],
            "created_at": now,
            "updated_at": now,
        }
        self._items.append(item)
        self._save()
        return item

    def get(self, item_id: str) -> _Item | None:
        """Return the item with *item_id*, or ``None`` if not found."""
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def update(
        self,
        item_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> _Item | None:
        """Update *content* and/or *tags* for an existing item.

        Returns the updated item, or ``None`` if *item_id* is not found.
        """
        item = self.get(item_id)
        if item is None:
            return None

        if content is not None:
            item["content"] = content
        if tags is not None:
            item["tags"] = tags
        item["updated_at"] = _utc_now_iso()
        self._save()
        return item

    def delete(self, item_id: str) -> bool:
        """Remove the item with *item_id*.

        Returns ``True`` if deleted, ``False`` if not found.
        """
        for idx, item in enumerate(self._items):
            if item["id"] == item_id:
                del self._items[idx]
                self._save()
                return True
        return False

    def search(
        self,
        query: str,
        source_cli: str | None = None,
    ) -> list[_Item]:
        """Keyword search across key, content, and tags (case-insensitive).

        Optionally filtered by *source_cli*.
        """
        q = query.lower()
        results: list[_Item] = []
        for item in self._items:
            if source_cli is not None and item["source_cli"] != source_cli:
                continue
            key_str = str(item.get("key", "")).lower()
            content_str = str(item.get("content", "")).lower()
            tags_raw = item.get("tags", [])
            tags_str = " ".join(str(t).lower() for t in tags_raw) if isinstance(tags_raw, list) else ""
            if q in key_str or q in content_str or q in tags_str:
                results.append(item)
        return results

    def list_all(self, source_cli: str | None = None) -> list[_Item]:
        """Return all items, optionally filtered by *source_cli*."""
        if source_cli is None:
            return list(self._items)
        return [i for i in self._items if i["source_cli"] == source_cli]

    def export_all(self) -> list[_Item]:
        """Return a copy of all items as a list."""
        return list(self._items)

    def import_items(self, items: list[_Item]) -> int:
        """Bulk import items, skipping any whose ``id`` already exists.

        Returns the number of items actually added.
        """
        existing_ids = {str(i["id"]) for i in self._items}
        added = 0
        for item in items:
            item_id = str(item.get("id", ""))
            if item_id and item_id not in existing_ids:
                self._items.append(item)
                existing_ids.add(item_id)
                added += 1
        if added:
            self._save()
        return added

    def count(self) -> int:
        """Return the total number of stored items."""
        return len(self._items)

    def clear(self) -> int:
        """Delete all items and return the count of deleted items."""
        n = len(self._items)
        self._items.clear()
        self._save()
        return n

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[_Item]:
        """Load items from the JSON file.  Returns empty list if missing."""
        path = Path(self.store_path)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, list):
                return raw  # type: ignore[return-value]
            return []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self) -> None:
        """Persist items to disk with atomic write (tmp + os.replace)."""
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(self._items, indent=2) + "\n")
        _ = os.replace(tmp_path, path)


def project_preference_signals(
    project_dir: str,
    *,
    store_path: str | None = None,
    max_signals: int = _PREFERENCE_SIGNAL_LIMIT,
) -> list[dict[str, Any]]:
    """Return bounded preference signals scoped to *project_dir*."""
    canonical_project = os.path.realpath(project_dir)
    if not canonical_project:
        return []

    limit = max(1, min(int(max_signals), _PREFERENCE_SIGNAL_LIMIT))
    store = MemoryStore(store_path=store_path)
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

    signal: dict[str, Any] = {
        "field": field,
        "value": value,
        "source": source,
        "confidence": confidence,
        "project_scope": canonical_project,
        "run_id": str(payload.get("run_id", "")).strip(),
        "updated_at": str(payload.get("updated_at", item.get("updated_at", ""))).strip(),
        "contradicted": contradicted,
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


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


__all__ = ["MemoryStore", "MemoryStoreFullError", "project_preference_signals"]
