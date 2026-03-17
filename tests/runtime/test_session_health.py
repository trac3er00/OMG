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
        "premature_fixer_score",
        "context_health",
        "verification_status",
        "recommended_action",
        "action_recommendations",
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
        {
            "contamination_score": 0.06,
            "injection_hits": 0,
            "overthinking_score": 0.0,
            "premature_fixer_score": 0.0,
            "clarification_sensitive": True,
        },
    )
    out = compute_session_health(str(tmp_path), run_id="warn-1")
    assert out["recommended_action"] == "reflect"
    assert out["action_recommendations"] == ["reflect"]


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
        {
            "contamination_score": 0.0,
            "injection_hits": 0,
            "overthinking_score": 0.16,
            "premature_fixer_score": 0.0,
            "clarification_sensitive": True,
        },
    )
    out = compute_session_health(str(tmp_path), run_id="over-2")
    assert out["recommended_action"] == "reflect"
    assert out["action_recommendations"] == ["reflect"]


def test_premature_fixer_score_triggers_reflect_for_clarification_sensitive_flow(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {
            "contamination_score": 0.0,
            "injection_hits": 0,
            "overthinking_score": 0.0,
            "premature_fixer_score": 0.51,
            "clarification_sensitive": True,
        },
    )
    out = compute_session_health(str(tmp_path), run_id="premature-1")
    assert out["recommended_action"] == "reflect"
    assert out["action_recommendations"] == ["reflect"]


def test_normal_flow_keeps_low_risk_with_same_scores(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {
            "contamination_score": 0.06,
            "injection_hits": 0,
            "overthinking_score": 0.16,
            "premature_fixer_score": 0.51,
            "clarification_sensitive": False,
        },
    )
    out = compute_session_health(str(tmp_path), run_id="normal-1")
    assert out["recommended_action"] == "continue"
    assert out["action_recommendations"] == ["continue"]


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


def test_stalled_worker_count_ignores_disconnected_ownership_records(tmp_path: Path) -> None:
    stale = {
        "schema": "WorkerHeartbeat",
        "run_id": "worker-old",
        "status": "alive",
        "heartbeat_count": 1,
        "last_heartbeat_at": "2026-03-01T00:00:00+00:00",
        "first_heartbeat_at": "2026-03-01T00:00:00+00:00",
        "metadata": {},
        "ownership": {
            "run_id": "worker-old",
            "active_run_id": "run-old",
            "merge_writer": {
                "authorized": False,
                "reason": "merge_writer_lock_missing",
            },
        },
    }
    _write_json(tmp_path / ".omg" / "state" / "worker-heartbeats" / "worker-old.json", stale)
    active_run_path = tmp_path / ".omg" / "shadow" / "active-run"
    active_run_path.parent.mkdir(parents=True, exist_ok=True)
    active_run_path.write_text("run-current\n", encoding="utf-8")

    out = compute_session_health(str(tmp_path), run_id="run-current")
    assert out["worker_stall"]["stalled_count"] == 0
    assert out["sources"]["worker_heartbeats"] is False


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


# ── Auto-action tests ──────────────────────────────────────────────────────

evaluate_auto_actions = import_module("runtime.session_health").evaluate_auto_actions
persist_auto_action_evidence = import_module("runtime.session_health").persist_auto_action_evidence


def test_auto_action_continue_for_healthy_session(tmp_path: Path) -> None:
    """Healthy session health produces continue auto-action."""
    health = compute_session_health(str(tmp_path), run_id="aa-healthy")
    result = evaluate_auto_actions(health)
    assert result["action"] == "continue"
    assert result["bounded"] is True
    assert result["review_route"] is None


def test_auto_action_pause_on_block_state(tmp_path: Path) -> None:
    """Block-level session health triggers pause auto-action."""
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.8, "injection_hits": 0, "overthinking_score": 0.0},
    )
    health = compute_session_health(str(tmp_path), run_id="aa-block")
    result = evaluate_auto_actions(health)
    assert result["action"] == "pause"
    assert result["bounded"] is True
    assert "contamination" in result["reason"].lower() or "block" in result["reason"].lower()


def test_auto_action_reflect_stays_bounded(tmp_path: Path) -> None:
    """Reflect-level auto-action stays bounded — no self-healing."""
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {
            "contamination_score": 0.06,
            "injection_hits": 0,
            "overthinking_score": 0.0,
            "premature_fixer_score": 0.0,
            "clarification_sensitive": True,
        },
    )
    health = compute_session_health(str(tmp_path), run_id="aa-reflect")
    result = evaluate_auto_actions(health)
    assert result["action"] == "reflect"
    assert result["bounded"] is True
    # Must NOT contain any self-healing or autonomous recovery indicators
    assert "self_healing" not in result
    assert "autonomous_recovery" not in result


def test_auto_action_require_review_on_destructive_profile(tmp_path: Path) -> None:
    """Destructive governed preferences in risky session triggers require-review."""
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.8, "injection_hits": 0, "overthinking_score": 0.0},
    )
    health = compute_session_health(str(tmp_path), run_id="aa-destructive")
    profile_risk = {
        "risk_level": "high",
        "destructive_entries": [{"field": "safety_mode", "value": "disable"}],
        "pending_confirmations": 1,
        "requires_review": True,
    }
    result = evaluate_auto_actions(health, profile_risk=profile_risk)
    assert result["action"] == "require-review"
    assert result["review_route"] == "/OMG:profile-review"
    assert result["bounded"] is True


def test_auto_action_warn_includes_profile_review_route(tmp_path: Path) -> None:
    """Warn-level auto-action with profile risk includes review route."""
    _write_json(
        tmp_path / ".omg" / "state" / "verification_controller" / "aa-warn.json",
        {"status": "error", "blockers": ["lint"], "evidence_links": []},
    )
    health = compute_session_health(str(tmp_path), run_id="aa-warn")
    profile_risk = {
        "risk_level": "medium",
        "destructive_entries": [],
        "pending_confirmations": 2,
        "requires_review": True,
    }
    result = evaluate_auto_actions(health, profile_risk=profile_risk)
    assert result["action"] in ("warn", "require-review")
    assert result["review_route"] == "/OMG:profile-review"
    assert result["bounded"] is True


def test_auto_action_evidence_persisted(tmp_path: Path) -> None:
    """Auto-action evidence is persisted to state directory."""
    health = compute_session_health(str(tmp_path), run_id="aa-persist")
    result = evaluate_auto_actions(health)
    path = persist_auto_action_evidence(str(tmp_path), result, run_id="aa-persist")
    assert Path(path).exists()
    persisted = json.loads(Path(path).read_text(encoding="utf-8"))
    assert persisted["action"] == "continue"
    assert persisted["bounded"] is True
    assert persisted["run_id"] == "aa-persist"


def test_auto_action_no_self_healing_on_any_action(tmp_path: Path) -> None:
    """No auto-action variant ever produces self-healing or autonomous recovery."""
    scenarios = [
        {},  # healthy
        {"contamination_score": 0.8},  # block
        {"contamination_score": 0.06, "clarification_sensitive": True},  # reflect
    ]
    for defense_state in scenarios:
        if defense_state:
            _write_json(
                tmp_path / ".omg" / "state" / "defense_state" / "current.json",
                defense_state,
            )
        health = compute_session_health(str(tmp_path), run_id="aa-noselfheal")
        result = evaluate_auto_actions(health)
        assert result["bounded"] is True, f"Unbounded action for {defense_state}"
        assert "self_healing" not in result
        assert "autonomous_recovery" not in result


def test_auto_action_evidence_includes_timestamp(tmp_path: Path) -> None:
    """Persisted evidence includes timestamp for audit trail."""
    health = compute_session_health(str(tmp_path), run_id="aa-ts")
    result = evaluate_auto_actions(health)
    path = persist_auto_action_evidence(str(tmp_path), result, run_id="aa-ts")
    persisted = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "timestamp" in persisted
    assert "T" in persisted["timestamp"]  # ISO format


# ── Pause/require-review evidence persistence ──────────────────────────────


def test_pause_state_persists_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.85, "injection_hits": 0, "overthinking_score": 0.0},
    )
    health = compute_session_health(str(tmp_path), run_id="pause-ev")
    result = evaluate_auto_actions(
        health, project_dir=str(tmp_path), run_id="pause-ev",
    )
    assert result["action"] == "pause"
    evidence_path = tmp_path / ".omg" / "state" / "session_health" / "actions" / "pause-ev.json"
    assert evidence_path.exists()
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["action"] == "pause"
    assert "contamination_risk=0.85 >= block threshold" in persisted["reason"]
    assert persisted["bounded"] is True


def test_require_review_state_persists_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"contamination_score": 0.85, "injection_hits": 0, "overthinking_score": 0.0},
    )
    health = compute_session_health(str(tmp_path), run_id="review-ev")
    profile_risk = {
        "risk_level": "high",
        "destructive_entries": [
            {"field": "safety_mode", "value": "disable"},
            {"field": "auto_approve", "value": "all"},
        ],
        "pending_confirmations": 2,
        "requires_review": True,
    }
    result = evaluate_auto_actions(
        health,
        profile_risk=profile_risk,
        project_dir=str(tmp_path),
        run_id="review-ev",
    )
    assert result["action"] == "require-review"
    evidence_path = tmp_path / ".omg" / "state" / "session_health" / "actions" / "review-ev.json"
    assert evidence_path.exists()
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["action"] == "require-review"
    assert "contamination_risk=0.85 >= block threshold" in persisted["reason"]
    assert "2 destructive preference(s) detected" in persisted["reason"]
    assert "profile_risk requires review" in persisted["reason"]


def test_healthy_session_continues_without_evidence(tmp_path: Path) -> None:
    health = compute_session_health(str(tmp_path), run_id="healthy-ev")
    result = evaluate_auto_actions(
        health, project_dir=str(tmp_path), run_id="healthy-ev",
    )
    assert result["action"] == "continue"
    evidence_path = tmp_path / ".omg" / "state" / "session_health" / "actions" / "healthy-ev.json"
    assert not evidence_path.exists()
