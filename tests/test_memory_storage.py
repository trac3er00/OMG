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

save_memory = cast(Callable[[str, str, str], str], getattr(memory_module, "save_memory"))
get_recent_memories = cast(Callable[..., str], getattr(memory_module, "get_recent_memories"))
rotate_memories = cast(Callable[..., int], getattr(memory_module, "rotate_memories"))


def test_save_memory_creates_file(tmp_path: Path):
    file_path = save_memory(str(tmp_path), "ses_test", "content")
    assert Path(file_path).exists()
    assert ".omg/state/memory/" in file_path


def test_save_memory_appends_if_exists(tmp_path: Path):
    file_path = save_memory(str(tmp_path), "ses_test", "first")
    _ = save_memory(str(tmp_path), "ses_test", "second")
    content = Path(file_path).read_text()
    assert "first" in content
    assert "second" in content


def test_save_memory_truncates_at_500(tmp_path: Path):
    long_content = "a" * 600
    file_path = save_memory(str(tmp_path), "ses_test", long_content)
    saved = Path(file_path).read_text()
    assert len(saved) <= 500


def test_rotate_memories_keeps_50(tmp_path: Path):
    memory_dir = tmp_path / ".omg" / "state" / "memory"
    _ = memory_dir.mkdir(parents=True)
    for index in range(55):
        _ = (memory_dir / f"2026-01-01-ses{index:03d}.md").write_text(f"file-{index}")
    _ = rotate_memories(str(tmp_path), 50)
    assert len(list(memory_dir.glob("*.md"))) == 50


def test_get_recent_memories_returns_under_300(tmp_path: Path):
    memory_dir = tmp_path / ".omg" / "state" / "memory"
    _ = memory_dir.mkdir(parents=True)
    for index in range(3):
        _ = (memory_dir / f"2026-01-0{index + 1}-ses{index}.md").write_text("x" * 200)
    summary = get_recent_memories(str(tmp_path), 5, 300)
    assert len(summary) <= 300


def test_get_recent_memories_empty_dir(tmp_path: Path):
    assert get_recent_memories(str(tmp_path)) == ""
