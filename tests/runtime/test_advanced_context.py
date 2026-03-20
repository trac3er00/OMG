"""Tests for NF3c, NF3d, NF3e — folder-scoped context, entry scoring, smart compact."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from runtime.context_engine import (
    get_folder_context,
    save_folder_context,
    score_context_entry,
    rank_context_entries,
    smart_compact,
)


# ---------------------------------------------------------------------------
# NF3c: Folder-scoped context tests
# ---------------------------------------------------------------------------


def test_get_folder_context_returns_none_for_missing(tmp_path: Path) -> None:
    """get_folder_context returns None when cache file doesn't exist."""
    result = get_folder_context(str(tmp_path), "/some/folder/path")
    assert result is None


def test_save_and_get_folder_context_round_trip(tmp_path: Path) -> None:
    """save_folder_context + get_folder_context round-trip works correctly."""
    folder_path = str(tmp_path / "src" / "components")
    content = "# Components\n\nThis folder contains React components."

    # Create the folder so mtime check works
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    # Save context
    cache_path = save_folder_context(str(tmp_path), folder_path, content)
    assert cache_path.endswith(".md")
    assert Path(cache_path).exists()

    # Get context back
    retrieved = get_folder_context(str(tmp_path), folder_path)
    assert retrieved == content


def test_get_folder_context_returns_none_when_stale(tmp_path: Path) -> None:
    """get_folder_context returns None when folder was modified after cache."""
    folder_path = str(tmp_path / "src")
    content = "# Source folder context"

    # Create folder
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    # Create a file inside the folder so we can modify its mtime
    inner_file = Path(folder_path) / "file.py"
    inner_file.write_text("# code")

    # Save context
    save_folder_context(str(tmp_path), folder_path, content)

    # Set an explicit future mtime on the inner file to trigger staleness
    # (avoids flakiness from filesystems with 1s timestamp resolution)
    future_time = time.time() + 10
    os.utime(inner_file, (future_time, future_time))

    # Cache should now be stale
    result = get_folder_context(str(tmp_path), folder_path)
    assert result is None


def test_save_folder_context_creates_context_directory(tmp_path: Path) -> None:
    """save_folder_context creates .omg/context directory if missing."""
    folder_path = "/any/path"
    content = "test content"

    cache_path = save_folder_context(str(tmp_path), folder_path, content)

    assert (tmp_path / ".omg" / "context").is_dir()
    assert Path(cache_path).exists()


# ---------------------------------------------------------------------------
# NF3d: Context entry scoring tests
# ---------------------------------------------------------------------------


def test_score_context_entry_recency_decay() -> None:
    """Recent entries score higher than older entries."""
    now = time.time()

    recent_entry = {"timestamp": now, "type": "general"}
    old_entry = {"timestamp": now - 7200, "type": "general"}  # 2 hours ago

    recent_score = score_context_entry(recent_entry)
    old_score = score_context_entry(old_entry)

    assert recent_score > old_score


def test_score_context_entry_task_relevance_boost() -> None:
    """Entries mentioning active task keywords score higher."""
    entry_relevant = {
        "timestamp": time.time(),
        "type": "general",
        "content": "Working on authentication module with OAuth",
    }
    entry_irrelevant = {
        "timestamp": time.time(),
        "type": "general",
        "content": "Working on database migrations",
    }

    active_task = "Fix authentication OAuth bug"

    relevant_score = score_context_entry(entry_relevant, active_task)
    irrelevant_score = score_context_entry(entry_irrelevant, active_task)

    assert relevant_score > irrelevant_score


def test_score_context_entry_type_boost_for_plan() -> None:
    """Plan/checklist entries get a +0.3 type boost."""
    now = time.time()

    plan_entry = {"timestamp": now, "type": "plan"}
    general_entry = {"timestamp": now, "type": "general"}

    plan_score = score_context_entry(plan_entry)
    general_score = score_context_entry(general_entry)

    # Plan should be at least 0.3 higher due to type boost
    assert plan_score >= general_score + 0.25  # Allow small margin


def test_score_context_entry_usage_boost() -> None:
    """Entries that were referenced get a usage boost."""
    now = time.time()

    referenced_entry = {"timestamp": now, "type": "general", "referenced": True}
    unreferenced_entry = {"timestamp": now, "type": "general", "referenced": False}

    referenced_score = score_context_entry(referenced_entry)
    unreferenced_score = score_context_entry(unreferenced_entry)

    assert referenced_score > unreferenced_score


def test_score_context_entry_clamped_to_range() -> None:
    """Score is always between 0.0 and 1.0."""
    # Entry with everything boosted
    now = time.time()
    max_entry = {
        "timestamp": now,
        "type": "plan",
        "referenced": True,
        "content": "authentication oauth fix",
    }

    score = score_context_entry(max_entry, "authentication oauth")
    assert 0.0 <= score <= 1.0


def test_rank_context_entries_sorts_correctly() -> None:
    """rank_context_entries sorts entries by score descending."""
    now = time.time()

    entries = [
        {"id": "low", "timestamp": now - 7200, "type": "general"},
        {"id": "high", "timestamp": now, "type": "plan"},
        {"id": "medium", "timestamp": now - 1800, "type": "general"},
    ]

    ranked = rank_context_entries(entries)

    assert len(ranked) == 3
    assert all("_score" in e for e in ranked)
    # Check descending order
    assert ranked[0]["_score"] >= ranked[1]["_score"] >= ranked[2]["_score"]
    # High scorer should be first (plan + recent)
    assert ranked[0]["id"] == "high"


def test_rank_context_entries_adds_score_field() -> None:
    """rank_context_entries adds _score field to each entry."""
    entries = [{"id": "a"}, {"id": "b"}]
    ranked = rank_context_entries(entries)

    for entry in ranked:
        assert "_score" in entry
        assert isinstance(entry["_score"], float)


def test_rank_context_entries_preserves_original_fields() -> None:
    """rank_context_entries preserves all original entry fields."""
    entries = [{"id": "test", "custom_field": "value", "nested": {"a": 1}}]
    ranked = rank_context_entries(entries)

    assert ranked[0]["id"] == "test"
    assert ranked[0]["custom_field"] == "value"
    assert ranked[0]["nested"] == {"a": 1}


# ---------------------------------------------------------------------------
# NF3e: Smart compact tests
# ---------------------------------------------------------------------------


def test_smart_compact_keeps_protected_entries(tmp_path: Path) -> None:
    """smart_compact never drops plan, checklist, or task_focus entries."""
    now = time.time()

    entries = [
        {"id": "plan", "type": "plan", "timestamp": now - 7200},  # Old but protected
        {"id": "checklist", "type": "checklist", "timestamp": now - 7200},
        {"id": "task", "type": "task_focus", "timestamp": now - 7200},
        {"id": "general1", "type": "general", "timestamp": now - 3600},
        {"id": "general2", "type": "general", "timestamp": now - 3600},
    ]

    result = smart_compact(str(tmp_path), entries, drop_ratio=0.8)

    kept_ids = {e["id"] for e in result["kept"]}

    # All protected entries must be kept regardless of drop_ratio
    assert "plan" in kept_ids
    assert "checklist" in kept_ids
    assert "task" in kept_ids


def test_smart_compact_drops_lowest_scoring(tmp_path: Path) -> None:
    """smart_compact drops lowest-scoring entries up to drop_ratio."""
    now = time.time()

    entries = [
        {"id": "high", "type": "general", "timestamp": now},  # Recent = high score
        {"id": "low1", "type": "general", "timestamp": now - 7200},  # Old = low score
        {"id": "low2", "type": "general", "timestamp": now - 7200},
        {"id": "low3", "type": "general", "timestamp": now - 7200},
        {"id": "low4", "type": "general", "timestamp": now - 7200},
    ]

    result = smart_compact(str(tmp_path), entries, drop_ratio=0.4)

    # With 5 entries and 40% drop, should drop 2
    assert result["dropped_count"] == 2
    assert result["kept_count"] == 3

    kept_ids = {e["id"] for e in result["kept"]}
    # High scorer should be kept
    assert "high" in kept_ids


def test_smart_compact_respects_drop_ratio(tmp_path: Path) -> None:
    """smart_compact drops approximately drop_ratio fraction of droppable entries."""
    now = time.time()

    # 10 general entries, no protected
    entries = [{"id": str(i), "type": "general", "timestamp": now - i * 100} for i in range(10)]

    result = smart_compact(str(tmp_path), entries, drop_ratio=0.5)

    # Should drop about 50% = 5 entries
    assert result["dropped_count"] == 5
    assert result["kept_count"] == 5


def test_smart_compact_returns_correct_structure(tmp_path: Path) -> None:
    """smart_compact returns dict with kept, dropped, kept_count, dropped_count."""
    entries = [{"id": "test", "type": "general"}]

    result = smart_compact(str(tmp_path), entries, drop_ratio=0.0)

    assert "kept" in result
    assert "dropped" in result
    assert "kept_count" in result
    assert "dropped_count" in result
    assert isinstance(result["kept"], list)
    assert isinstance(result["dropped"], list)
    assert isinstance(result["kept_count"], int)
    assert isinstance(result["dropped_count"], int)


def test_smart_compact_handles_empty_entries(tmp_path: Path) -> None:
    """smart_compact handles empty entry list gracefully."""
    result = smart_compact(str(tmp_path), [], drop_ratio=0.5)

    assert result["kept"] == []
    assert result["dropped"] == []
    assert result["kept_count"] == 0
    assert result["dropped_count"] == 0


def test_smart_compact_protects_unsolved_entries(tmp_path: Path) -> None:
    """smart_compact never drops unsolved/blocker/error entries."""
    now = time.time()

    entries = [
        {"id": "unsolved", "type": "unsolved", "timestamp": now - 7200},
        {"id": "blocker", "type": "blocker", "timestamp": now - 7200},
        {"id": "error", "type": "error", "timestamp": now - 7200},
        {"id": "general", "type": "general", "timestamp": now},
    ]

    result = smart_compact(str(tmp_path), entries, drop_ratio=1.0)  # Try to drop everything

    kept_ids = {e["id"] for e in result["kept"]}

    # All critical types must be kept
    assert "unsolved" in kept_ids
    assert "blocker" in kept_ids
    assert "error" in kept_ids


def test_smart_compact_honors_protected_flag(tmp_path: Path) -> None:
    """smart_compact keeps entries with 'protected': True."""
    now = time.time()

    entries = [
        {"id": "marked", "type": "general", "timestamp": now - 7200, "protected": True},
        {"id": "unmarked", "type": "general", "timestamp": now - 7200, "protected": False},
    ]

    result = smart_compact(str(tmp_path), entries, drop_ratio=1.0)

    kept_ids = {e["id"] for e in result["kept"]}
    assert "marked" in kept_ids


def test_smart_compact_adds_score_to_entries(tmp_path: Path) -> None:
    """smart_compact adds _score field to kept and dropped entries."""
    entries = [
        {"id": "a", "type": "general"},
        {"id": "b", "type": "general"},
    ]

    result = smart_compact(str(tmp_path), entries, drop_ratio=0.5)

    for entry in result["kept"] + result["dropped"]:
        assert "_score" in entry
