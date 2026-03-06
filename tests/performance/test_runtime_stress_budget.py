"""Stress-budget tests for runtime evidence and tmux reuse summaries."""
from __future__ import annotations

from pathlib import Path

from runtime.tmux_session_manager import build_tmux_reuse_report
from tests.perf import hook_latency as hook_latency_bench


def test_build_runtime_stress_budget_payload_summarizes_regressions(tmp_path: Path):
    payload = hook_latency_bench.build_runtime_stress_budget_payload(
        str(tmp_path),
        samples=[
            {"name": "dispatch-a", "avg_ms": 120.0, "peak_memory_mb": 48.0},
            {"name": "dispatch-b", "avg_ms": 390.0, "peak_memory_mb": 96.0},
        ],
        tmux_report=build_tmux_reuse_report(reused_sessions=2, total_sessions=5),
    )

    assert payload["schema"] == "OmgRuntimeStressBudget"
    assert payload["summary"]["sample_count"] == 2
    assert payload["summary"]["over_latency_budget"] == ["dispatch-b"]
    assert payload["summary"]["over_memory_budget"] == []
    assert payload["summary"]["tmux_reuse_within_budget"] is False
    assert payload["summary"]["within_budget"] is False


def test_build_tmux_reuse_report_tracks_ratio_and_budget():
    report = build_tmux_reuse_report(reused_sessions=7, total_sessions=10)

    assert report["schema"] == "OmgTmuxReuseReport"
    assert report["reuse_ratio"] == 0.7
    assert report["within_budget"] is True
