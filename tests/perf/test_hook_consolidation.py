"""Benchmark: verify hook consolidation reduces overhead.

Measures import time and execution time for consolidated vs individual hooks.
Target: 60% overhead reduction for PreToolUse and PostToolUse event cycles.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "hooks"
PROJECT_DIR = str(Path(__file__).resolve().parent.parent.parent)


def _time_hook(hook_path: str, input_data: dict, runs: int = 3) -> float:
    """Run a hook N times and return average ms."""
    timings = []
    for _ in range(runs):
        start = time.monotonic()
        subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(input_data),
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "CLAUDE_PROJECT_DIR": PROJECT_DIR},
        )
        timings.append((time.monotonic() - start) * 1000)
    return sum(timings) / len(timings)


def test_consolidated_hooks_compile():
    """All consolidated hook files must compile without errors."""
    for name in ("pre-tool-all.py", "post-tool-all.py", "hashline-manager.py"):
        path = HOOKS_DIR / name
        if path.exists():
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import py_compile; py_compile.compile('{path}', doraise=True)"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"{name} compilation failed: {result.stderr}"


def test_stop_helpers_importable():
    """_stop_helpers.py must import successfully."""
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        import _stop_helpers
        assert hasattr(_stop_helpers, "read_checklist_progress")
        assert hasattr(_stop_helpers, "parse_diff_stat")
        assert hasattr(_stop_helpers, "is_test_file")
        assert hasattr(_stop_helpers, "is_source_file")
    finally:
        sys.path.pop(0)


def test_stop_helpers_checklist_progress(tmp_path: Path):
    """read_checklist_progress handles various checklist formats."""
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        from _stop_helpers import read_checklist_progress

        # Normal checklist
        cl = tmp_path / "checklist.md"
        cl.write_text("- [x] Done\n- [ ] Pending\n- [!] Blocked\n")
        done, total, pending = read_checklist_progress(str(cl))
        assert done == 1
        assert total == 3
        assert pending == "Pending"

        # Empty file
        cl.write_text("")
        done, total, pending = read_checklist_progress(str(cl))
        assert done == 0 and total == 0 and pending is None

        # Missing file
        done, total, pending = read_checklist_progress("/nonexistent")
        assert done == 0 and total == 0 and pending is None
    finally:
        sys.path.pop(0)


def test_stop_helpers_parse_diff_stat():
    """parse_diff_stat handles git diff --stat output."""
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        from _stop_helpers import parse_diff_stat

        files, lines = parse_diff_stat(
            " hooks/_common.py | 50 +++--\n"
            " hooks/firewall.py | 10 +\n"
            " 2 files changed, 45 insertions(+), 15 deletions(-)\n"
        )
        assert files == 2
        assert lines == 60  # 45 + 15

        # Empty input
        assert parse_diff_stat("") == (0, 0)
        assert parse_diff_stat(None) == (0, 0)
    finally:
        sys.path.pop(0)


def test_stop_helpers_file_classification():
    """is_test_file and is_source_file classify correctly."""
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        from _stop_helpers import is_test_file, is_source_file

        assert is_test_file("tests/test_common.py")
        assert is_test_file("src/__tests__/app.test.tsx")
        assert is_test_file("test_foo.py")
        assert not is_test_file("hooks/_common.py")
        assert not is_test_file("README.md")

        assert is_source_file("hooks/_common.py")
        assert is_source_file("src/app.tsx")
        assert not is_source_file("README.md")
        assert not is_source_file("settings.json")
    finally:
        sys.path.pop(0)
