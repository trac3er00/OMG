#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Productivity patterns analyzer for OMG state data."""
from __future__ import annotations

import os
from datetime import datetime
from typing import TypeAlias

from hooks.query import (
    get_failure_hotspots,
    get_file_heatmap,
    get_session_summary,
    get_tool_stats,
)


JsonMap: TypeAlias = dict[str, object]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if isinstance(value, (int, float, str)):
            return int(value)
        return default
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if isinstance(value, (int, float, str)):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _last_edited_iso(project_dir: str, rel_file: str) -> str:
    path = os.path.join(project_dir, rel_file)
    if not os.path.exists(path):
        return ""
    try:
        ts = os.path.getmtime(path)
    except OSError:
        return ""
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _analyze_hotspots(project_dir: str, heatmap: JsonMap) -> list[JsonMap]:
    if not isinstance(heatmap, dict):
        return []

    out: list[JsonMap] = []
    for file_path, stats in heatmap.items():
        if not isinstance(file_path, str) or not isinstance(stats, dict):
            continue
        edit_count = _safe_int(stats.get("edits", 0), 0)
        if edit_count <= 5:
            continue
        out.append(
            {
                "file": file_path,
                "edit_count": edit_count,
                "last_edited": _last_edited_iso(project_dir, file_path),
            }
        )

    out.sort(key=lambda item: (-_safe_int(item.get("edit_count", 0), 0), str(item.get("file", ""))))
    return out


def _analyze_error_trends(failures: JsonMap, days: int) -> JsonMap:
    if not isinstance(failures, dict) or not failures:
        return {"trend": "stable", "recent_rate": 0.0, "baseline_rate": 0.0}

    total_failures = 0
    recent_failures = 0
    for rec in failures.values():
        if not isinstance(rec, dict):
            continue
        count = max(_safe_int(rec.get("count", 0), 0), 0)
        total_failures += count
        recent_errors = rec.get("last_3_errors", [])
        if isinstance(recent_errors, list):
            recent_failures += min(len(recent_errors), count)
        else:
            recent_failures += min(3, count)

    baseline_total = max(total_failures - recent_failures, 0)
    baseline_days = max(days - 1, 1)
    recent_rate = float(recent_failures)
    baseline_rate = baseline_total / baseline_days

    if baseline_rate == 0.0 and recent_rate == 0.0:
        trend = "stable"
    elif baseline_rate == 0.0:
        trend = "increasing"
    else:
        delta_ratio = (recent_rate - baseline_rate) / baseline_rate
        if delta_ratio > 0.10:
            trend = "increasing"
        elif delta_ratio < -0.10:
            trend = "decreasing"
        else:
            trend = "stable"

    return {
        "trend": trend,
        "recent_rate": round(recent_rate, 3),
        "baseline_rate": round(baseline_rate, 3),
    }


def _analyze_tool_shifts(tool_stats: JsonMap) -> list[JsonMap]:
    if not isinstance(tool_stats, dict) or not tool_stats:
        return []

    counts: list[float] = []
    for stats in tool_stats.values():
        if not isinstance(stats, dict):
            continue
        counts.append(max(_safe_float(stats.get("count", 0), 0.0), 0.0))

    if not counts:
        return []

    baseline = sum(counts) / len(counts)
    if baseline <= 0.0:
        return []

    shifts: list[JsonMap] = []
    for tool, stats in tool_stats.items():
        if not isinstance(tool, str) or not isinstance(stats, dict):
            continue
        count = max(_safe_float(stats.get("count", 0), 0.0), 0.0)
        change_pct = ((count - baseline) / baseline) * 100.0
        if abs(change_pct) <= 20.0:
            continue
        shifts.append(
            {
                "tool": tool,
                "change_pct": round(change_pct, 2),
                "direction": "up" if change_pct > 0 else "down",
            }
        )

    shifts.sort(key=lambda item: -abs(_safe_float(item.get("change_pct", 0.0), 0.0)))
    return shifts


def _analyze_session_trends(summary: JsonMap) -> JsonMap:
    duration_sec = 0.0
    if isinstance(summary, dict):
        duration_sec = max(_safe_float(summary.get("duration", 0), 0.0), 0.0)
    avg_duration_min = duration_sec / 60.0

    if avg_duration_min > 90.0:
        trend = "longer"
    elif 0.0 < avg_duration_min < 30.0:
        trend = "shorter"
    else:
        trend = "stable"

    return {
        "avg_duration_min": round(avg_duration_min, 2),
        "trend": trend,
    }


def _build_summary_md(report: JsonMap) -> str:
    hotspots_obj = report.get("hotspots", [])
    hotspots = hotspots_obj if isinstance(hotspots_obj, list) else []

    error_trends_obj = report.get("error_trends", {})
    error_trends = error_trends_obj if isinstance(error_trends_obj, dict) else {}

    tool_shifts_obj = report.get("tool_usage_shifts", [])
    tool_shifts = tool_shifts_obj if isinstance(tool_shifts_obj, list) else []

    session_trends_obj = report.get("session_trends", {})
    session_trends = session_trends_obj if isinstance(session_trends_obj, dict) else {}

    lines = [
        "# Productivity Patterns",
        "",
        "## Refactoring Hotspots",
    ]
    if hotspots:
        for item in hotspots:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('file', '')}`: {item.get('edit_count', 0)} edits "
                f"(last edited: {item.get('last_edited', 'n/a') or 'n/a'})"
            )
    else:
        lines.append("- None detected.")

    lines.extend(
        [
            "",
            "## Error Trends",
            (
                "- Trend: "
                f"{error_trends.get('trend', 'stable')} "
                f"(recent_rate={error_trends.get('recent_rate', 0.0)}, "
                f"baseline_rate={error_trends.get('baseline_rate', 0.0)})"
            ),
            "",
            "## Tool Usage Shifts",
        ]
    )
    if tool_shifts:
        for item in tool_shifts:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('tool', 'unknown')}: {item.get('change_pct', 0.0)}% "
                f"({item.get('direction', 'up')})"
            )
    else:
        lines.append("- No significant (>20%) usage shifts.")

    lines.extend(
        [
            "",
            "## Session Length Trends",
            (
                "- Avg duration: "
                f"{session_trends.get('avg_duration_min', 0.0)} min "
                f"({session_trends.get('trend', 'stable')})"
            ),
        ]
    )
    return "\n".join(lines)


def analyze_patterns(project_dir: str, days: int = 7) -> JsonMap:
    """Return productivity pattern report from query-layer analytics."""
    try:
        import importlib
        _common = importlib.import_module("hooks._common")
        if not _common.get_feature_flag("SESSION_ANALYTICS", default=False):
            return {
                "hotspots": [],
                "error_trends": {"trend": "stable", "recent_rate": 0.0, "baseline_rate": 0.0},
                "tool_usage_shifts": [],
                "session_trends": {"avg_duration_min": 0.0, "trend": "stable"},
                "summary_md": "",
            }
    except Exception:
        pass
    
    analysis_days = max(_safe_int(days, 7), 1)

    try:
        heatmap_raw = get_file_heatmap(project_dir)
        heatmap = heatmap_raw if isinstance(heatmap_raw, dict) else {}
    except Exception:
        heatmap = {}

    try:
        failures_raw = get_failure_hotspots(project_dir)
        failures = failures_raw if isinstance(failures_raw, dict) else {}
    except Exception:
        failures = {}

    try:
        tool_stats_raw = get_tool_stats(project_dir, hours=analysis_days * 24)
        tool_stats = tool_stats_raw if isinstance(tool_stats_raw, dict) else {}
    except Exception:
        tool_stats = {}

    try:
        session_summary_raw = get_session_summary(project_dir)
        session_summary = session_summary_raw if isinstance(session_summary_raw, dict) else {}
    except Exception:
        session_summary = {}

    report: JsonMap = {
        "hotspots": _analyze_hotspots(project_dir, heatmap),
        "error_trends": _analyze_error_trends(failures, analysis_days),
        "tool_usage_shifts": _analyze_tool_shifts(tool_stats),
        "session_trends": _analyze_session_trends(session_summary),
    }
    report["summary_md"] = _build_summary_md(report)
    return report


__all__ = ["analyze_patterns"]
