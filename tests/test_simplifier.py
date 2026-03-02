"""Tests for the code simplifier (anti-AI-slop) — Task 17.

Part 1: Discipline injection in prompt-enhancer contains anti-slop text.
Part 2: CHECK 7 in stop_dispatcher detects slop, advisory only (never blocks).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Load stop_dispatcher module
_SPEC = importlib.util.spec_from_file_location(
    "stop_dispatcher",
    ROOT / "hooks" / "stop_dispatcher.py",
)
assert _SPEC and _SPEC.loader
stop_dispatcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stop_dispatcher)


def _base_data() -> dict[str, Any]:
    return {
        "_stop_ctx": {
            "recent_entries": [],
            "recent_commands": [],
            "has_source_writes": False,
            "has_material_writes": False,
            "source_write_entries": [],
        },
        "_stop_advisories": [],
    }


# ── Part 1: Discipline injection ──────────────────────────


def test_discipline_contains_antislop():
    """Discipline injection must contain anti-slop keywords."""
    result = subprocess.run(
        [sys.executable, "hooks/prompt-enhancer.py"],
        input=json.dumps({"tool_input": {"user_message": "implement auth"}}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        data = json.loads(result.stdout)
        ci = data.get("contextInjection", "").lower()
        keywords = ["noise comment", "generic name", "clean", "minimal"]
        assert any(
            kw in ci for kw in keywords
        ), f"Missing anti-slop keywords in: {ci[:200]}"


# ── Part 2: CHECK 7 — code simplifier ─────────────────────


def test_check7_detects_high_comment_ratio(monkeypatch, tmp_path, capsys):
    """File with >40% comments triggers advisory in stderr."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    sloppy = tmp_path / "bloated.py"
    # 6 comment lines + 3 code lines = 66% comments
    sloppy.write_text(
        "# get user\n"
        "# set value\n"
        "# return result\n"
        "# check auth\n"
        "# create session\n"
        "# delete old\n"
        "x = 1\n"
        "y = 2\n"
        "z = 3\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(sloppy)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []  # Never blocks
    captured = capsys.readouterr()
    assert "@simplifier" in captured.err
    assert "comment lines" in captured.err


def test_check7_does_not_block(monkeypatch, tmp_path, capsys):
    """Slop detected → stdout has no 'decision', only stderr advisories."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    sloppy = tmp_path / "sloppy.py"
    sloppy.write_text(
        "# get user\n# set value\n# return result\n# check auth\n"
        "# create session\n# delete old\n"
        "def get_data(temp):\n    return temp\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(sloppy)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    # Must return empty list (never blocks)
    assert result == []
    captured = capsys.readouterr()
    # Advisory in stderr
    assert "@simplifier" in captured.err
    # No decision in stdout
    assert "decision" not in captured.out


def test_check7_detects_generic_names(monkeypatch, tmp_path, capsys):
    """Generic names in def/let/const/var lines trigger advisory."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    src = tmp_path / "handler.py"
    src.write_text(
        "import os\n"
        "\n"
        "def process_data(item):\n"
        "    return item\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(src)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []
    captured = capsys.readouterr()
    assert "@simplifier" in captured.err
    assert "generic name" in captured.err


def test_check7_detects_noise_comments(monkeypatch, tmp_path, capsys):
    """Noise comments like '# get user' trigger advisory."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    src = tmp_path / "service.py"
    src.write_text(
        "# get user from database\n"
        "def fetch_user(user_id):\n"
        "    return db.query(user_id)\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(src)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []
    captured = capsys.readouterr()
    assert "@simplifier" in captured.err
    assert "noise comment" in captured.err


def test_check7_skips_large_files(monkeypatch, tmp_path, capsys):
    """Files >10KB are skipped."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    big = tmp_path / "big.py"
    # Write >10KB of comments
    big.write_text("# comment\n" * 2000)
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(big)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []
    captured = capsys.readouterr()
    assert captured.err == ""  # No advisory for large files


def test_check7_respects_feature_flag(monkeypatch, tmp_path, capsys):
    """Feature flag off → no analysis."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: False
    )
    sloppy = tmp_path / "sloppy.py"
    sloppy.write_text("# comment\n" * 10 + "x = 1\n")
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(sloppy)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []
    captured = capsys.readouterr()
    assert captured.err == ""


def test_check7_clean_file_no_advisory(monkeypatch, tmp_path, capsys):
    """Clean file with no slop → no advisory."""
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_a, **_kw: True
    )
    clean = tmp_path / "clean.py"
    clean.write_text(
        "def calculate_tax(income, rate):\n"
        "    # Complex tax bracket logic for EU compliance\n"
        "    if income < 10000:\n"
        "        return 0\n"
        "    return income * rate\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(clean)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []
    captured = capsys.readouterr()
    assert captured.err == ""
