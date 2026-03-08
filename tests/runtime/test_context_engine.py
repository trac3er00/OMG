"""Tests for runtime.context_engine — bounded context packet builder."""

import json
from pathlib import Path

from runtime.context_engine import ContextEngine


REQUIRED_KEYS = {"summary", "artifact_pointers", "budget", "delta_only", "run_id"}
BUDGET_KEYS = {"max_chars", "used_chars"}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_packet_has_required_keys(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-1")
    assert REQUIRED_KEYS.issubset(pkt.keys())
    assert BUDGET_KEYS.issubset(pkt["budget"].keys())


def test_budget_respected(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "architecture_signal" / "latest.json",
        {"summary": "x" * 2000},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-2")
    assert pkt["budget"]["max_chars"] == 1000
    assert pkt["budget"]["used_chars"] <= 1000
    assert len(pkt["summary"]) <= 1000


def test_delta_only_flag_preserved(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-3", delta_only=True)
    assert pkt["delta_only"] is True


def test_delta_only_false_by_default(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-4")
    assert pkt["delta_only"] is False


def test_missing_state_files_degrade_gracefully(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-5")
    assert pkt["summary"] == "no context signals available"
    assert pkt["artifact_pointers"] == []
    assert pkt["budget"]["used_chars"] == 0
    assert pkt["run_id"] == "t-5"


def test_artifact_pointers_are_paths_not_content(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "low", "actions": []},
    )
    _write_json(
        tmp_path / ".omg" / "state" / ".context-pressure.json",
        {"tool_count": 42, "is_high": False},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-6")

    for ptr in pkt["artifact_pointers"]:
        assert isinstance(ptr, str)
        assert not ptr.startswith("{")
        assert "/" in ptr or "\\" in ptr


def test_summary_includes_defense_state(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "high", "actions": ["warn", "flag"]},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-7")
    assert "defense" in pkt["summary"]
    assert "high" in pkt["summary"]


def test_summary_includes_verification(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "background-verification.json",
        {"status": "running", "blockers": ["lint"]},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-8")
    assert "verification" in pkt["summary"]
    assert "running" in pkt["summary"]


def test_summary_includes_pressure(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / ".context-pressure.json",
        {"tool_count": 200, "is_high": True},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-9")
    assert "pressure" in pkt["summary"]
    assert "200" in pkt["summary"]


def test_packet_persisted_to_disk(tmp_path):
    engine = ContextEngine(str(tmp_path))
    engine.build_packet(run_id="t-10")
    packet_path = tmp_path / ".omg" / "state" / "context_engine_packet.json"
    assert packet_path.exists()
    data = json.loads(packet_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "t-10"


def test_delta_only_no_change_reports_no_changes(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "low", "actions": []},
    )
    engine = ContextEngine(str(tmp_path))
    engine.build_packet(run_id="t-11")
    pkt2 = engine.build_packet(run_id="t-11", delta_only=True)
    assert pkt2["delta_only"] is True
    assert "no changes" in pkt2["summary"]


def test_run_id_preserved(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="my-custom-run-42")
    assert pkt["run_id"] == "my-custom-run-42"


def test_malformed_json_degrades(tmp_path):
    bad_path = tmp_path / ".omg" / "state" / "defense_state" / "current.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{invalid json!!!", encoding="utf-8")
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-12")
    assert "summary" in pkt
    assert isinstance(pkt["artifact_pointers"], list)
