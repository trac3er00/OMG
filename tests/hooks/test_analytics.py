# pyright: reportMissingImports=false
"""Tests for hooks/_analytics.py productivity pattern analyzer (Task 18)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hooks._analytics as analytics


def _patch_empty(monkeypatch):
    monkeypatch.setattr(analytics, "get_file_heatmap", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_failure_hotspots", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_tool_stats", lambda _project_dir, hours=None: {})
    monkeypatch.setattr(
        analytics,
        "get_session_summary",
        lambda _project_dir: {
            "duration": 0,
            "tool_calls": 0,
            "success_rate": 0.0,
            "files_modified": 0,
            "tests_run": 0,
            "tokens_used": 0,
            "cost_usd": 0.0,
        },
    )


def test_analyze_patterns_empty_data_returns_valid_structure(tmp_path: Path, monkeypatch) -> None:
    _patch_empty(monkeypatch)

    result = analytics.analyze_patterns(str(tmp_path))

    assert set(result.keys()) == {
        "hotspots",
        "error_trends",
        "tool_usage_shifts",
        "session_trends",
        "summary_md",
    }
    assert result["hotspots"] == []
    assert result["tool_usage_shifts"] == []
    assert result["error_trends"]["trend"] == "stable"
    assert result["error_trends"]["recent_rate"] == 0.0
    assert result["error_trends"]["baseline_rate"] == 0.0
    assert result["session_trends"] == {"avg_duration_min": 0.0, "trend": "stable"}
    assert isinstance(result["summary_md"], str)
    assert len(result["summary_md"]) > 0


def test_hotspots_include_only_files_with_more_than_five_edits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tracked = tmp_path / "tracked.py"
    _ = tracked.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(
        analytics,
        "get_file_heatmap",
        lambda _project_dir: {
            "tracked.py": {"reads": 1, "writes": 0, "edits": 6},
            "cold.py": {"reads": 2, "writes": 1, "edits": 5},
        },
    )
    monkeypatch.setattr(analytics, "get_failure_hotspots", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_tool_stats", lambda _project_dir, hours=None: {})
    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 0})

    result = analytics.analyze_patterns(str(tmp_path))

    assert len(result["hotspots"]) == 1
    assert result["hotspots"][0]["file"] == "tracked.py"
    assert result["hotspots"][0]["edit_count"] == 6
    assert isinstance(result["hotspots"][0]["last_edited"], str)
    assert result["hotspots"][0]["last_edited"]


def test_error_trend_detects_increasing_rates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_file_heatmap", lambda _project_dir: {})
    monkeypatch.setattr(
        analytics,
        "get_failure_hotspots",
        lambda _project_dir: {
            "Bash:pytest": {
                "count": 12,
                "last_3_errors": ["e1", "e2", "e3"],
                "escalated": True,
            },
            "Write:file": {
                "count": 9,
                "last_3_errors": ["a", "b", "c"],
                "escalated": True,
            },
        },
    )
    monkeypatch.setattr(analytics, "get_tool_stats", lambda _project_dir, hours=None: {})
    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 0})

    trends = analytics.analyze_patterns(str(tmp_path), days=7)["error_trends"]
    assert trends["trend"] == "increasing"
    assert trends["recent_rate"] > trends["baseline_rate"]


def test_error_trend_detects_decreasing_rates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_file_heatmap", lambda _project_dir: {})
    monkeypatch.setattr(
        analytics,
        "get_failure_hotspots",
        lambda _project_dir: {
            "Bash:pytest": {
                "count": 40,
                "last_3_errors": ["e1"],
                "escalated": True,
            }
        },
    )
    monkeypatch.setattr(analytics, "get_tool_stats", lambda _project_dir, hours=None: {})
    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 0})

    trends = analytics.analyze_patterns(str(tmp_path), days=7)["error_trends"]
    assert trends["trend"] == "decreasing"
    assert trends["recent_rate"] < trends["baseline_rate"]


def test_tool_usage_shifts_include_gt_20_percent_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_file_heatmap", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_failure_hotspots", lambda _project_dir: {})
    monkeypatch.setattr(
        analytics,
        "get_tool_stats",
        lambda _project_dir, hours=None: {
            "Bash": {"count": 100, "success_rate": 0.9, "avg_tokens": 1.0},
            "Read": {"count": 20, "success_rate": 1.0, "avg_tokens": 1.0},
            "Edit": {"count": 80, "success_rate": 1.0, "avg_tokens": 1.0},
        },
    )
    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 0})

    shifts = analytics.analyze_patterns(str(tmp_path))["tool_usage_shifts"]
    by_tool = {entry["tool"]: entry for entry in shifts}

    assert "Bash" in by_tool
    assert "Read" in by_tool
    assert by_tool["Bash"]["direction"] == "up"
    assert by_tool["Read"]["direction"] == "down"
    assert abs(by_tool["Bash"]["change_pct"]) > 20.0
    assert abs(by_tool["Read"]["change_pct"]) > 20.0


def test_session_trends_detect_longer_and_shorter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_file_heatmap", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_failure_hotspots", lambda _project_dir: {})
    monkeypatch.setattr(analytics, "get_tool_stats", lambda _project_dir, hours=None: {})

    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 7200})
    longer = analytics.analyze_patterns(str(tmp_path))["session_trends"]
    assert longer["avg_duration_min"] == 120.0
    assert longer["trend"] == "longer"

    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 600})
    shorter = analytics.analyze_patterns(str(tmp_path))["session_trends"]
    assert shorter["avg_duration_min"] == 10.0
    assert shorter["trend"] == "shorter"


def test_summary_markdown_contains_all_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        analytics,
        "get_file_heatmap",
        lambda _project_dir: {"a.py": {"reads": 0, "writes": 0, "edits": 6}},
    )
    monkeypatch.setattr(
        analytics,
        "get_failure_hotspots",
        lambda _project_dir: {
            "Bash:pytest": {"count": 10, "last_3_errors": ["e1", "e2", "e3"], "escalated": True}
        },
    )
    monkeypatch.setattr(
        analytics,
        "get_tool_stats",
        lambda _project_dir, hours=None: {
            "Bash": {"count": 100, "success_rate": 1.0, "avg_tokens": 1.0},
            "Read": {"count": 20, "success_rate": 1.0, "avg_tokens": 1.0},
        },
    )
    monkeypatch.setattr(analytics, "get_session_summary", lambda _project_dir: {"duration": 3600})

    md = analytics.analyze_patterns(str(tmp_path))["summary_md"]
    assert "# Productivity Patterns" in md
    assert "## Refactoring Hotspots" in md
    assert "## Error Trends" in md
    assert "## Tool Usage Shifts" in md
    assert "## Session Length Trends" in md
