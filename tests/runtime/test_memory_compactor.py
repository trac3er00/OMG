from __future__ import annotations

from collections.abc import Callable
import importlib
from pathlib import Path
from typing import Protocol, cast


class CompactionResultLike(Protocol):
    before_entries: int
    after_entries: int
    before_bytes: int
    after_bytes: int
    removed: int
    archived: int
    categories_compacted: list[str]
    dry_run: bool

    def reduction_pct(self) -> float: ...


class MemoryCompactorLike(Protocol):
    def __init__(self, project_dir: str = ".", max_bytes: int = 10 * 1024 * 1024) -> None: ...

    def compact(
        self,
        entries_by_category: dict[str, list[dict[str, object]]],
        dry_run: bool = False,
    ) -> CompactionResultLike: ...


_module = importlib.import_module("runtime.memory_compactor")
CompactionResult = cast(type[CompactionResultLike], getattr(_module, "CompactionResult"))
MemoryCompactor = cast(type[MemoryCompactorLike], getattr(_module, "MemoryCompactor"))


def _make_entry(category: str, **kwargs: object) -> dict[str, object]:
    from datetime import datetime, timezone

    base: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
    }
    base.update(kwargs)
    return base


def test_decisions_never_compacted(tmp_path: Path) -> None:
    mc = MemoryCompactor(str(tmp_path))
    entries = {"decisions": [_make_entry("decisions", decision=f"d{i}", rationale="r") for i in range(10)]}
    result = mc.compact(entries)
    assert result.removed == 0
    assert result.after_entries == 10


def test_old_failures_compacted(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    mc = MemoryCompactor(str(tmp_path))
    old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()
    entries = {
        "failures": [
            {"what": "old failure", "why": "cause", "timestamp": old_ts},
            {"what": "recent failure", "why": "cause", "timestamp": recent_ts},
        ]
    }
    result = mc.compact(entries)
    assert result.after_entries == 1
    assert result.removed == 1


def test_open_loops_never_compacted(tmp_path: Path) -> None:
    mc = MemoryCompactor(str(tmp_path))
    entries = {
        "open_loops": [_make_entry("open_loops", task=f"t{i}", status="pending") for i in range(5)]
    }
    result = mc.compact(entries)
    assert result.removed == 0
    assert result.after_entries == 5


def test_preferences_deduplicated(tmp_path: Path) -> None:
    mc = MemoryCompactor(str(tmp_path))
    entries = {
        "preferences": [
            {"preference": "naming", "value": "camelCase", "timestamp": "2024-01-01T00:00:00+00:00"},
            {"preference": "naming", "value": "snake_case", "timestamp": "2024-01-02T00:00:00+00:00"},
        ]
    }
    result = mc.compact(entries)
    assert result.after_entries == 1
    assert result.removed == 1


def test_dry_run_no_changes(tmp_path: Path) -> None:
    mc = MemoryCompactor(str(tmp_path))
    entries = {
        "preferences": [
            {"preference": "x", "value": "1", "timestamp": "2024-01-01T00:00:00+00:00"},
            {"preference": "x", "value": "2", "timestamp": "2024-01-02T00:00:00+00:00"},
        ]
    }
    result = mc.compact(entries, dry_run=True)
    assert result.dry_run is True
    assert result.removed == 1
    archive_files = list(tmp_path.rglob("compacted-*.jsonl"))
    assert len(archive_files) == 0


def test_reduction_percentage() -> None:
    result = CompactionResult(
        before_entries=10,
        after_entries=7,
        before_bytes=1000,
        after_bytes=700,
        removed=3,
        archived=3,
        categories_compacted=["failures"],
        dry_run=False,
    )
    assert abs(result.reduction_pct() - 30.0) < 0.1
