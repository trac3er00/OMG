"""Memory compactor for OMG with selective retention policy.

Retention rules:
- Keep ALL decisions (category='decisions')
- Keep recent failures (last 30 days in 'failures' category)
- Keep ALL open loops ('open_loops' category)
- Compact old preferences (deduplicate)
Budget: max 10MB default, auto-compact at 80%
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time


JsonObject = dict[str, object]

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_WARN_THRESHOLD = 0.80
_FAILURE_RETENTION_DAYS = 30
_ALWAYS_KEEP = frozenset({"decisions", "open_loops"})  # never compact these


@dataclass
class CompactionResult:
    before_entries: int
    after_entries: int
    before_bytes: int
    after_bytes: int
    removed: int
    archived: int
    categories_compacted: list[str]
    dry_run: bool

    def reduction_pct(self) -> float:
        if self.before_entries == 0:
            return 0.0
        return (self.removed / self.before_entries) * 100


class MemoryCompactor:
    """Selective memory compactor with category-aware retention."""

    project_dir: str
    max_bytes: int
    _store_path: Path
    _archive_path: Path

    def __init__(self, project_dir: str = ".", max_bytes: int = _DEFAULT_MAX_BYTES):
        self.project_dir = project_dir
        self.max_bytes = max_bytes
        self._store_path = Path(project_dir) / ".omg" / "state" / "memory"
        self._archive_path = Path(project_dir) / ".omg" / "state" / "memory-archive"

    def _get_memory_size(self) -> int:
        """Return total size in bytes of all memory entries."""
        total = 0
        if self._store_path.exists():
            for file_path in self._store_path.rglob("*.json*"):
                try:
                    total += file_path.stat().st_size
                except OSError:
                    pass
        return total

    def should_compact(self) -> bool:
        """Return True if memory has exceeded 80% of budget."""
        return self._get_memory_size() > (self.max_bytes * _WARN_THRESHOLD)

    def _filter_by_category(
        self,
        entries: list[JsonObject],
        category: str,
    ) -> tuple[list[JsonObject], list[JsonObject]]:
        """Separate entries into (keep, archive) based on category rules."""
        if category in _ALWAYS_KEEP:
            return entries, []

        if category == "failures":
            cutoff_ts = datetime.now(timezone.utc).timestamp() - (
                _FAILURE_RETENTION_DAYS * 86400
            )
            kept_entries: list[JsonObject] = []
            archived_entries: list[JsonObject] = []
            for entry in entries:
                timestamp = _parse_timestamp(entry.get("timestamp"))
                if timestamp is None or timestamp >= cutoff_ts:
                    kept_entries.append(entry)
                else:
                    archived_entries.append(entry)
            return kept_entries, archived_entries

        if category == "preferences":
            latest_by_key: dict[str, JsonObject] = {}
            archived_entries: list[JsonObject] = []
            for entry in sorted(entries, key=_timestamp_sort_key):
                key = _preference_key(entry)
                previous = latest_by_key.get(key)
                if previous is not None:
                    archived_entries.append(previous)
                latest_by_key[key] = entry
            return list(latest_by_key.values()), archived_entries

        return entries, []

    def compact(
        self,
        entries_by_category: dict[str, list[JsonObject]],
        dry_run: bool = False,
        respect_tier_boundaries: bool = True,
    ) -> CompactionResult:
        """Compact memory entries according to retention rules.

        Args:
            entries_by_category: dict mapping category → list of entries
            dry_run: if True, compute result without modifying anything

        Returns:
            CompactionResult with before/after counts and metrics
        """
        before_total = sum(len(entries) for entries in entries_by_category.values())
        before_bytes = sum(
            len(json.dumps(entry, sort_keys=True))
            for entries in entries_by_category.values()
            for entry in entries
        )

        kept: dict[str, list[JsonObject]] = {}
        archived: dict[str, list[JsonObject]] = {}
        categories_compacted: list[str] = []

        for category, entries in entries_by_category.items():
            ship_entries: list[JsonObject] = []
            category_entries = entries
            if respect_tier_boundaries:
                category_entries = []
                for entry in entries:
                    if str(entry.get("_memory_tier", "")).lower() == "ship":
                        ship_entries.append(entry)
                    else:
                        category_entries.append(entry)

            kept_entries, archived_entries = self._filter_by_category(
                category_entries, category
            )
            if ship_entries:
                kept_entries = [*kept_entries, *ship_entries]
            kept[category] = kept_entries
            archived[category] = archived_entries
            if archived_entries:
                categories_compacted.append(category)

        after_total = sum(len(entries) for entries in kept.values())
        after_bytes = sum(
            len(json.dumps(entry, sort_keys=True))
            for entries in kept.values()
            for entry in entries
        )
        total_archived = sum(len(entries) for entries in archived.values())

        if not dry_run and categories_compacted:
            self._archive_path.mkdir(parents=True, exist_ok=True)
            archive_file = self._archive_path / f"compacted-{int(time.time())}.jsonl"
            with archive_file.open("w", encoding="utf-8") as handle:
                for category, entries in archived.items():
                    for entry in entries:
                        archived_entry = dict(entry)
                        archived_entry["_archived_from"] = category
                        _ = handle.write(
                            json.dumps(archived_entry, sort_keys=True) + "\n"
                        )

        return CompactionResult(
            before_entries=before_total,
            after_entries=after_total,
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            removed=before_total - after_total,
            archived=total_archived,
            categories_compacted=categories_compacted,
            dry_run=dry_run,
        )


def _parse_timestamp(raw_value: object) -> float | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value).timestamp()
    except ValueError:
        return None


def _timestamp_sort_key(entry: JsonObject) -> str:
    value = entry.get("timestamp")
    if isinstance(value, str):
        return value
    return ""


def _preference_key(entry: JsonObject) -> str:
    for key_name in ("preference", "key"):
        value = entry.get(key_name)
        if isinstance(value, str) and value:
            return value
    return json.dumps(entry, sort_keys=True)[:40]
