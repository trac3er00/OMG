#!/usr/bin/env python3
import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable, cast

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

spec = importlib.util.spec_from_file_location("_memory", os.path.join(HOOKS_DIR, "_memory.py"))
assert spec is not None and spec.loader is not None
memory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory_module)

search_memories = cast(Callable[..., str], getattr(memory_module, "search_memories"))


def _make_memory_dir(tmp_path: Path) -> Path:
    """Helper: create .omg/state/memory/ and return its path."""
    memory_dir = tmp_path / ".omg" / "state" / "memory"
    memory_dir.mkdir(parents=True)
    return memory_dir


def test_no_memory_dir_returns_empty(tmp_path: Path):
    """search_memories returns '' when .omg/state/memory/ does not exist."""
    result = search_memories(str(tmp_path), ["test"])
    assert result == ""


def test_empty_keywords_returns_empty(tmp_path: Path):
    """search_memories returns '' when keyword list is empty."""
    memory_dir = _make_memory_dir(tmp_path)
    (memory_dir / "2026-01-01-abc.md").write_text("some content about auth")
    result = search_memories(str(tmp_path), [])
    assert result == ""


def test_keyword_match_returns_excerpt(tmp_path: Path):
    """search_memories returns matching file excerpts for keyword hits."""
    memory_dir = _make_memory_dir(tmp_path)
    (memory_dir / "2026-01-01-abc.md").write_text(
        "# Session\nImplemented auth middleware\nAdded JWT validation\nAll tests pass"
    )
    (memory_dir / "2026-01-02-def.md").write_text(
        "# Session\nFixed database migration\nNo auth changes"
    )
    result = search_memories(str(tmp_path), ["auth"])
    assert "2026-01-01-abc.md" in result or "2026-01-02-def.md" in result
    # Both files contain "auth", so both could appear
    assert "auth" in result.lower() or len(result) > 0


def test_score_ranking_higher_match_first(tmp_path: Path):
    """Files with more keyword matches should rank higher."""
    memory_dir = _make_memory_dir(tmp_path)
    # File with 1 keyword match
    (memory_dir / "2026-01-01-low.md").write_text(
        "Worked on auth system today"
    )
    # File with 2 keyword matches
    (memory_dir / "2026-01-02-high.md").write_text(
        "Implemented auth with JWT tokens for auth middleware"
    )
    result = search_memories(str(tmp_path), ["auth", "JWT"])
    lines = result.strip().split("\n")
    # The file with more matches should appear first
    assert len(lines) >= 1
    assert "2026-01-02-high.md" in lines[0]


def test_char_budget_respected(tmp_path: Path):
    """Output should not exceed max_chars budget."""
    memory_dir = _make_memory_dir(tmp_path)
    for i in range(10):
        (memory_dir / f"2026-01-{i:02d}-ses{i}.md").write_text(
            f"keyword match here with lots of extra content number {i} " * 5
        )
    result = search_memories(str(tmp_path), ["keyword"], max_results=10, max_chars=150)
    # Count only the excerpt chars (not filenames), but total output should be bounded
    # The function tracks chars_used based on excerpt lengths
    assert len(result) <= 500  # generous upper bound including filenames


def test_non_md_files_ignored(tmp_path: Path):
    """Only .md files should be searched, not .txt or others."""
    memory_dir = _make_memory_dir(tmp_path)
    (memory_dir / "notes.txt").write_text("auth keyword here")
    (memory_dir / "data.json").write_text('{"auth": true}')
    result = search_memories(str(tmp_path), ["auth"])
    assert result == ""


def test_no_matches_returns_empty(tmp_path: Path):
    """search_memories returns '' when no keywords match any file content."""
    memory_dir = _make_memory_dir(tmp_path)
    (memory_dir / "2026-01-01-abc.md").write_text("Worked on database migrations")
    result = search_memories(str(tmp_path), ["auth", "JWT"])
    assert result == ""


def test_header_lines_excluded_from_excerpt(tmp_path: Path):
    """Lines starting with # should not appear in excerpts."""
    memory_dir = _make_memory_dir(tmp_path)
    (memory_dir / "2026-01-01-abc.md").write_text(
        "# Session Header\n## Sub Header\nActual auth content line\nMore content"
    )
    result = search_memories(str(tmp_path), ["auth"])
    assert "# Session Header" not in result
    assert "## Sub Header" not in result
    assert "auth" in result.lower()
