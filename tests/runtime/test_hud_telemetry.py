from __future__ import annotations
import pytest
from runtime.hud_telemetry import HUDTelemetry, HUDMetrics


def test_initial_metrics_zero(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    metrics = hud.get_current()
    assert metrics["tokens_used"] == 0
    assert metrics["api_calls"] == 0
    assert metrics["failures"] == 0


def test_record_api_call_accumulates(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    hud.record_api_call(tokens_in=100, tokens_out=50, cost_usd=0.001)
    metrics = hud.get_current()
    assert metrics["tokens_used"] == 150
    assert metrics["api_calls"] == 1
    assert abs(metrics["cost_usd"] - 0.001) < 0.0001


def test_record_tool_call_tracks_failures(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    hud.record_tool_call(tool="Write", success=True)
    hud.record_tool_call(tool="Bash", success=False)
    metrics = hud.get_current()
    assert metrics["tool_calls"] == 2
    assert metrics["failures"] == 1


def test_update_mode(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    hud.update_mode("governed")
    metrics = hud.get_current()
    assert metrics["mode"] == "governed"


def test_snapshot_writes_to_file(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    hud.record_api_call(tokens_in=10)
    snap = hud.snapshot()
    assert isinstance(snap, HUDMetrics)
    telemetry_file = tmp_path / ".omg" / "state" / "hud-telemetry.jsonl"
    assert telemetry_file.exists()


def test_metrics_has_required_fields(tmp_path: "Path") -> None:
    hud = HUDTelemetry(str(tmp_path))
    metrics = hud.get_current()
    for field in (
        "session_id",
        "tokens_used",
        "cost_usd",
        "api_calls",
        "mode",
        "failures",
    ):
        assert field in metrics
