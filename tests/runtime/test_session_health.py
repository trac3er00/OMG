"""Tests for runtime.session_health — session health monitor."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

compute_session_health = import_module("runtime.session_health").compute_session_health


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Key presence ────────────────────────────────────────────────────────────

def test_compute_returns_all_required_keys(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="h-1")
    for key in (
        "contamination_risk",
        "overthinking_score",
        "context_health",
        "verification_status",
        "recommended_action",
        "run_id",
        "thresholds",
    ):
        assert key in out, f"missing key: {key}"


def test_compute_returns_schema_and_version(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="h-2")
    assert out["schema"] == "SessionHealth"
    assert out["schema_version"] == "1.0.0"
    assert out["run_id"] == "h-2"


# ── Graceful degradation ───────────────────────────────────────────────────

def test_graceful_degradation_when_no_sources_exist(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="empty-1")
    assert out["contamination_risk"] == 0.0
    assert out["overthinking_score"] == 0.0
    assert out["context_health"] == 1.0
    assert out["verification_status"] == "unknown"
    assert out["recommended_action"] == "continue"


def test_graceful_degradation_with_corrupt_defense_state(tmp_path: Path) -> None:
    defense_path = tmp_path / ".omg" / "state" / "defense_state" / "current.json"
    defense_path.parent.mkdir(parents=True, exist_ok=True)
    defense_path.write_text("NOT JSON", encoding="utf-8")

    out = compute_session_health(str(tmp_path), run_id="corrupt-1")
    assert out["contamination_risk"] == 0.0
    assert out["recommended_action"] == "continue"


# ── Threshold enforcement ──────────────────────────────────────────────────

def test_high_contamination_triggers_block(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.8, "injection_hits": 0, "overthinking_score": 0.0},
    )
    out = compute_session_health(str(tmp_path), run_id="block-1")
    assert out["contamination_risk"] >= 0.7
    assert out["recommended_action"] == "block"


def test_injection_hits_escalate_contamination(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.0, "injection_hits": 3, "overthinking_score": 0.0},
    )
    out = compute_session_health(str(tmp_path), run_id="inject-1")
    assert out["contamination_risk"] >= 0.7
    assert out["recommended_action"] == "block"


def test_medium_contamination_triggers_reflect(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.35, "injection_hits": 0, "overthinking_score": 0.0},
    )
    out = compute_session_health(str(tmp_path), run_id="warn-1")
    assert out["recommended_action"] == "reflect"


def test_high_overthinking_triggers_block(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.0, "injection_hits": 0, "overthinking_score": 0.9},
    )
    out = compute_session_health(str(tmp_path), run_id="over-1")
    assert out["recommended_action"] == "block"


def test_moderate_overthinking_triggers_reflect(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.0, "injection_hits": 0, "overthinking_score": 0.55},
    )
    out = compute_session_health(str(tmp_path), run_id="over-2")
    assert out["recommended_action"] == "reflect"


def test_high_context_pressure_degrades_health(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / ".context-pressure.json",
        {"tool_count": 200, "threshold": 150, "is_high": True},
    )
    out = compute_session_health(str(tmp_path), run_id="pressure-1")
    assert out["context_health"] < 1.0
    assert out["overthinking_score"] > 0.0


def test_verification_error_triggers_warn(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "verification_controller" / "verify-1.json",
        {"status": "error", "blockers": ["lint"], "evidence_links": []},
    )
    out = compute_session_health(str(tmp_path), run_id="verify-1")
    assert out["verification_status"] == "error"
    assert out["recommended_action"] == "warn"


def test_verification_reads_background_fallback(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "background-verification.json",
        {"schema": "BackgroundVerificationState", "status": "ok", "blockers": [], "evidence_links": []},
    )
    out = compute_session_health(str(tmp_path), run_id="bg-1")
    assert out["verification_status"] == "ok"


# ── Journal step counting ─────────────────────────────────────────────────

def test_journal_entries_counted(tmp_path: Path) -> None:
    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (journal_dir / f"step-{i}.json").write_text("{}", encoding="utf-8")
    out = compute_session_health(str(tmp_path), run_id="journal-1")
    assert out["journal_steps"] == 5


def test_many_journal_entries_degrade_context_health(tmp_path: Path) -> None:
    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    for i in range(55):
        (journal_dir / f"step-{i}.json").write_text("{}", encoding="utf-8")
    out = compute_session_health(str(tmp_path), run_id="journal-2")
    assert out["context_health"] < 1.0


# ── State persistence ──────────────────────────────────────────────────────

def test_result_persisted_to_state_file(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="persist-1")
    persisted_path = tmp_path / ".omg" / "state" / "session_health" / "persist-1.json"
    assert persisted_path.exists()
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert persisted["run_id"] == "persist-1"
    assert persisted["contamination_risk"] == out["contamination_risk"]


# ── Sources reporting ──────────────────────────────────────────────────────

def test_sources_report_availability(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.1},
    )
    out = compute_session_health(str(tmp_path), run_id="sources-1")
    assert out["sources"]["defense_state"] is True
    assert out["sources"]["context_pressure"] is False
    assert out["sources"]["journal"] is False


# ── Production caller integration ──────────────────────────────────────────

def test_session_health_includes_status_field(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="status-1")
    assert "status" in out, "missing status field"
    assert out["status"] in {"pending", "running", "ok", "error", "blocked"}


def test_session_health_persisted_via_runtime_contracts(tmp_path: Path) -> None:
    out = compute_session_health(str(tmp_path), run_id="contracts-1")
    persisted_path = tmp_path / ".omg" / "state" / "session_health" / "contracts-1.json"
    assert persisted_path.exists()
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == "SessionHealth"
    assert persisted["schema_version"] == "1.0.0"
    assert "status" in persisted
    assert persisted["status"] in {"pending", "running", "ok", "error", "blocked"}
    assert persisted["run_id"] == "contracts-1"


def test_coordinator_mutate_produces_session_health(tmp_path: Path) -> None:
    from runtime.release_run_coordinator import ReleaseRunCoordinator

    coord = ReleaseRunCoordinator(str(tmp_path))
    result = coord.begin()
    run_id = str(result["run_id"])
    coord.mutate(
        run_id=run_id,
        tool="Edit",
        metadata={"file": "x.py"},
        goal="fix bug",
        available_tools=["Edit", "Read"],
    )
    health_path = tmp_path / ".omg" / "state" / "session_health" / f"{run_id}.json"
    assert health_path.exists(), "mutate() should produce session health state"
    persisted = json.loads(health_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == "SessionHealth"
    assert persisted["run_id"] == run_id


def test_coordinator_mutate_updates_defense_state(tmp_path: Path) -> None:
    from runtime.release_run_coordinator import ReleaseRunCoordinator

    coord = ReleaseRunCoordinator(str(tmp_path))
    result = coord.begin()
    run_id = str(result["run_id"])
    coord.mutate(
        run_id=run_id,
        tool="Edit",
        metadata={"file": "x.py"},
        goal="fix bug",
        available_tools=["Edit", "Read"],
    )
    defense_path = tmp_path / ".omg" / "state" / "defense_state" / "current.json"
    assert defense_path.exists(), "mutate() should refresh defense state"
    defense = json.loads(defense_path.read_text(encoding="utf-8"))
    assert "risk_level" in defense
    assert "updated_at" in defense
