# pyright: reportMissingImports=false
"""Tests for hooks/query.py unified query layer (Task 15)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hooks.query import (
    get_escalation_effectiveness,
    get_failure_hotspots,
    get_file_heatmap,
    get_session_summary,
    get_tool_stats,
)


def _ledger_dir(project_dir: Path) -> Path:
    path = project_dir / ".omg" / "state" / "ledger"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(path: Path, *entries: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            if isinstance(entry, str):
                f.write(entry + "\n")
            else:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def test_get_tool_stats_missing_ledger_returns_empty_dict(tmp_path: Path) -> None:
    assert get_tool_stats(str(tmp_path)) == {}


def test_get_tool_stats_aggregates_success_and_tokens(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    _append_jsonl(
        ledger / "tool-ledger.jsonl",
        {"ts": "2026-03-04T10:00:00+00:00", "tool": "Bash", "exit_code": 0},
        {"ts": "2026-03-04T10:01:00+00:00", "tool": "Bash", "exit_code": 1},
        {"ts": "2026-03-04T10:02:00+00:00", "tool": "Read"},
    )
    _append_jsonl(
        ledger / "cost-ledger.jsonl",
        {"tool": "Bash", "tokens_in": 100, "tokens_out": 20, "cost_usd": 0.01},
        {"tool": "Bash", "tokens_in": 80, "tokens_out": 20, "cost_usd": 0.01},
        {"tool": "Read", "tokens_in": 10, "tokens_out": 5, "cost_usd": 0.001},
    )

    stats = get_tool_stats(str(tmp_path))
    assert stats["Bash"]["count"] == 2
    assert stats["Bash"]["success_rate"] == 0.5
    assert stats["Bash"]["avg_tokens"] == 110.0
    assert stats["Read"]["count"] == 1
    assert stats["Read"]["success_rate"] == 1.0
    assert stats["Read"]["avg_tokens"] == 15.0


def test_get_tool_stats_skips_malformed_lines(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    _append_jsonl(
        ledger / "tool-ledger.jsonl",
        {"tool": "Bash", "exit_code": 0},
        "not-json",
        {"tool": "Bash", "exit_code": 1},
    )
    _append_jsonl(
        ledger / "cost-ledger.jsonl",
        "{broken",
        {"tool": "Bash", "tokens_in": 20, "tokens_out": 10},
    )

    stats = get_tool_stats(str(tmp_path))
    assert stats["Bash"]["count"] == 2
    assert stats["Bash"]["avg_tokens"] == 30.0


def test_get_tool_stats_incremental_offsets_do_not_double_count(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    tool_path = ledger / "tool-ledger.jsonl"
    cost_path = ledger / "cost-ledger.jsonl"

    _append_jsonl(tool_path, {"tool": "Bash", "exit_code": 0})
    _append_jsonl(cost_path, {"tool": "Bash", "tokens_in": 10, "tokens_out": 10})

    first = get_tool_stats(str(tmp_path))
    second = get_tool_stats(str(tmp_path))
    assert first["Bash"]["count"] == 1
    assert second["Bash"]["count"] == 1

    _append_jsonl(tool_path, {"tool": "Bash", "exit_code": 1})
    _append_jsonl(cost_path, {"tool": "Bash", "tokens_in": 20, "tokens_out": 0})
    third = get_tool_stats(str(tmp_path))
    assert third["Bash"]["count"] == 2


def test_get_failure_hotspots_missing_returns_empty_dict(tmp_path: Path) -> None:
    assert get_failure_hotspots(str(tmp_path)) == {}


def test_get_failure_hotspots_formats_last_errors_and_escalation(tmp_path: Path) -> None:
    tracker = {
        "Bash:pytest": {
            "count": 4,
            "errors": ["e1", "e2", "e3", "e4"],
        },
        "Write:app.py": {
            "count": 1,
            "errors": ["single"],
        },
    }
    path = _ledger_dir(tmp_path) / "failure-tracker.json"
    path.write_text(json.dumps(tracker), encoding="utf-8")

    hotspots = get_failure_hotspots(str(tmp_path))
    assert hotspots["Bash:pytest"]["count"] == 4
    assert hotspots["Bash:pytest"]["last_3_errors"] == ["e2", "e3", "e4"]
    assert hotspots["Bash:pytest"]["escalated"] is True
    assert hotspots["Write:app.py"]["escalated"] is False


def test_get_session_summary_empty_project_returns_zeroes(tmp_path: Path) -> None:
    summary = get_session_summary(str(tmp_path))
    assert summary == {
        "duration": 0,
        "tool_calls": 0,
        "success_rate": 0.0,
        "files_modified": 0,
        "tests_run": 0,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }


def test_get_session_summary_aggregates_ledgers(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    _append_jsonl(
        ledger / "tool-ledger.jsonl",
        {
            "ts": "2026-03-04T10:00:00+00:00",
            "tool": "Bash",
            "command": "python3 -m pytest tests/hooks/test_query.py",
            "exit_code": 0,
        },
        {
            "ts": "2026-03-04T10:10:00+00:00",
            "tool": "Write",
            "file": "hooks/query.py",
            "success": True,
        },
        {
            "ts": "2026-03-04T10:20:00+00:00",
            "tool": "Edit",
            "file": "tests/hooks/test_query.py",
            "success": False,
        },
    )
    _append_jsonl(
        ledger / "cost-ledger.jsonl",
        {"tool": "Bash", "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.003},
        {"tool": "Write", "tokens_in": 10, "tokens_out": 10, "cost_usd": 0.001},
    )

    summary = get_session_summary(str(tmp_path))
    assert summary["duration"] == 1200
    assert summary["tool_calls"] == 3
    assert summary["success_rate"] == 2 / 3
    assert summary["files_modified"] == 2
    assert summary["tests_run"] == 1
    assert summary["tokens_used"] == 170
    assert summary["cost_usd"] == 0.004


def test_get_session_summary_incremental_does_not_repeat(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    tool_path = ledger / "tool-ledger.jsonl"

    _append_jsonl(
        tool_path,
        {"ts": "2026-03-04T10:00:00+00:00", "tool": "Bash", "exit_code": 0},
    )
    one = get_session_summary(str(tmp_path))
    two = get_session_summary(str(tmp_path))
    assert one["tool_calls"] == 1
    assert two["tool_calls"] == 1

    _append_jsonl(
        tool_path,
        {"ts": "2026-03-04T10:01:00+00:00", "tool": "Bash", "exit_code": 1},
    )
    three = get_session_summary(str(tmp_path))
    assert three["tool_calls"] == 2


def test_get_escalation_effectiveness_missing_returns_zeroes(tmp_path: Path) -> None:
    assert get_escalation_effectiveness(str(tmp_path)) == {
        "escalations": 0,
        "resolved": 0,
        "unresolved": 0,
    }


def test_get_escalation_effectiveness_counts_active_escalations(tmp_path: Path) -> None:
    tracker = {
        "Bash:pytest": {"count": 5},
        "Bash:flake8": {"count": 3},
        "Write:main.py": {"count": 1},
    }
    path = _ledger_dir(tmp_path) / "failure-tracker.json"
    path.write_text(json.dumps(tracker), encoding="utf-8")

    result = get_escalation_effectiveness(str(tmp_path))
    assert result["escalations"] == 2
    assert result["resolved"] == 0
    assert result["unresolved"] == 2


def test_get_file_heatmap_missing_returns_empty(tmp_path: Path) -> None:
    assert get_file_heatmap(str(tmp_path)) == {}


def test_get_file_heatmap_counts_reads_writes_edits_incrementally(tmp_path: Path) -> None:
    ledger = _ledger_dir(tmp_path)
    path = ledger / "tool-ledger.jsonl"
    _append_jsonl(
        path,
        {"tool": "Read", "file": "hooks/query.py"},
        {"tool": "Write", "file": "hooks/query.py", "success": True},
        {"tool": "Edit", "file": "hooks/query.py", "success": True},
    )
    first = get_file_heatmap(str(tmp_path))
    second = get_file_heatmap(str(tmp_path))
    assert first["hooks/query.py"] == {"reads": 1, "writes": 1, "edits": 1}
    assert second["hooks/query.py"] == {"reads": 1, "writes": 1, "edits": 1}

    _append_jsonl(path, {"tool": "Read", "file": "hooks/query.py"})
    third = get_file_heatmap(str(tmp_path))
    assert third["hooks/query.py"] == {"reads": 2, "writes": 1, "edits": 1}
