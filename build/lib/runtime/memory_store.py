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
_Item = dict[str, Any]


class MemoryStore:
    """Thread-unsafe, file-backed key/content store with JSON persistence."""

    def __init__(self, store_path: str | None = None) -> None:
        if store_path is None:
            store_path = str(Path.home() / ".omg" / "shared-memory" / "store.json")
        self.store_path = store_path
        self._items: list[_Item] = self._load()

    def add(self, key: str, content: str, source_cli: str, tags: list[str] | None = None) -> _Item:
        if self.count() >= _MAX_ITEMS:
            raise MemoryStoreFullError(
                f"Memory store is full ({_MAX_ITEMS} items). Delete items before adding new ones."
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
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def update(self, item_id: str, *, content: str | None = None, tags: list[str] | None = None) -> _Item | None:
        item = self.get(item_id)
        if item is None:
            return None

        if content is not None:
            item["content"] = content
        if tags is not None:
            item["tags"] = list(tags)
        item["updated_at"] = _utc_now_iso()
        self._save()
        return item

    def delete(self, item_id: str) -> bool:
        for idx, item in enumerate(self._items):
            if item["id"] == item_id:
                del self._items[idx]
                self._save()
                return True
        return False

    def search(self, query: str, source_cli: str | None = None) -> list[_Item]:
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
        if source_cli is None:
            return list(self._items)
        return [item for item in self._items if item["source_cli"] == source_cli]

    def export_all(self) -> list[_Item]:
        return list(self._items)

    def import_items(self, items: list[_Item]) -> int:
        existing_ids = {str(item["id"]) for item in self._items}
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
        return len(self._items)

    def clear(self) -> int:
        deleted = len(self._items)
        if deleted:
            self._items = []
            self._save()
        return deleted

    def _load(self) -> list[_Item]:
        path = Path(self.store_path)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return []
        return raw if isinstance(raw, list) else []

    def _save(self) -> None:
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(self._items, indent=2) + "\n", encoding="utf-8")
        _ = os.replace(tmp_path, path)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["MemoryStore", "MemoryStoreFullError"]
