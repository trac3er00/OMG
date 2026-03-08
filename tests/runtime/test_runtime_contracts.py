# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
from pathlib import Path

from runtime.runtime_contracts import (
    default_layout,
    make_run_path,
    read_run_state,
    schema_versions,
    write_run_state,
)


def test_default_layout_contains_expected_state_modules(tmp_path: Path) -> None:
    layout = default_layout(str(tmp_path))
    paths = layout["paths"]

    for module in (
        "verification_controller",
        "interaction_journal",
        "context_engine",
        "defense_state",
    ):
        assert module in paths
        assert f".omg/state/{module}" in paths[module].replace("\\", "/")


def test_schema_versions_exposes_all_contracts() -> None:
    versions = schema_versions()

    for module in (
        "verification_controller",
        "interaction_journal",
        "context_engine",
        "defense_state",
    ):
        assert module in versions
        assert isinstance(versions[module]["schema_name"], str)
        assert isinstance(versions[module]["version"], str)
        assert isinstance(versions[module]["required_fields"], list)


def test_make_run_path_uses_run_scoped_state_layout(tmp_path: Path) -> None:
    path = make_run_path(str(tmp_path), "verification_controller", "run-abc123")
    expected = tmp_path / ".omg" / "state" / "verification_controller" / "run-abc123.json"
    assert path == expected


def test_write_read_run_state_round_trip(tmp_path: Path) -> None:
    payload = {
        "status": "running",
        "blockers": ["missing_proof"],
        "evidence_links": [".omg/evidence/run-abc123.json"],
        "progress": {"step": 1, "total": 3},
    }

    path = write_run_state(str(tmp_path), "verification_controller", "run-abc123", payload)
    loaded = read_run_state(str(tmp_path), "verification_controller", "run-abc123")

    assert Path(path).exists()
    assert loaded is not None
    assert loaded["schema"] == "VerificationControllerState"
    assert loaded["schema_version"] == "1.0.0"
    assert loaded["run_id"] == "run-abc123"
    assert loaded["status"] == "running"
    assert loaded["blockers"] == ["missing_proof"]
    assert loaded["evidence_links"] == [".omg/evidence/run-abc123.json"]
    assert loaded["progress"] == {"step": 1, "total": 3}
    assert "updated_at" in loaded


def test_read_run_state_returns_none_for_missing_or_malformed_files(tmp_path: Path) -> None:
    assert read_run_state(str(tmp_path), "context_engine", "run-missing") is None

    path = make_run_path(str(tmp_path), "context_engine", "run-bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("not-json", encoding="utf-8")

    assert read_run_state(str(tmp_path), "context_engine", "run-bad") is None


def test_background_verification_compat_reader_supports_legacy_state(tmp_path: Path) -> None:
    legacy_path = tmp_path / ".omg" / "state" / "background-verification.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    _ = legacy_path.write_text(
        json.dumps(
            {
                "schema": "BackgroundVerificationState",
                "schema_version": 2,
                "run_id": "run-legacy",
                "status": "ok",
                "blockers": [],
                "evidence_links": [],
                "progress": {},
                "updated_at": "2026-03-08T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    payload = read_run_state(str(tmp_path), "verification_controller", "run-legacy")

    assert payload is not None
    assert payload["schema"] == "VerificationControllerState"
    assert payload["schema_version"] == "1.0.0"
    assert payload["status"] == "ok"
    assert payload["run_id"] == "run-legacy"


def test_default_layout_contains_new_state_modules(tmp_path: Path) -> None:
    layout = default_layout(str(tmp_path))
    paths = layout["paths"]
    for module in ("session_health", "council_verdicts", "rollback_manifest", "release_run"):
        assert module in paths, f"module {module!r} missing from default_layout"
        assert f".omg/state/{module}" in paths[module].replace("\\", "/")


def test_schema_versions_exposes_new_contracts() -> None:
    versions = schema_versions()
    for module in ("session_health", "council_verdicts", "rollback_manifest", "release_run"):
        assert module in versions, f"schema {module!r} missing from schema_versions"
        sv = versions[module]
        assert isinstance(sv["schema_name"], str) and sv["schema_name"]
        assert isinstance(sv["version"], str) and sv["version"]
        assert isinstance(sv["required_fields"], list)
        for base in ("schema", "schema_version", "run_id", "status", "updated_at"):
            assert base in sv["required_fields"], f"{module} missing base field {base!r}"



def test_session_health_write_read_round_trip(tmp_path: Path) -> None:
    payload = {
        "status": "ok",
        "contamination_risk": 0.1,
        "overthinking_score": 0.2,
        "context_health": 0.9,
        "verification_status": "ok",
        "recommended_action": "continue",
    }
    path = write_run_state(str(tmp_path), "session_health", "run-sh1", payload)
    loaded = read_run_state(str(tmp_path), "session_health", "run-sh1")

    assert Path(path).exists()
    assert loaded is not None
    assert loaded["schema"] == "SessionHealth"
    assert loaded["schema_version"] == "1.0.0"
    assert loaded["run_id"] == "run-sh1"
    assert loaded["status"] == "ok"
    assert loaded["contamination_risk"] == 0.1
    assert loaded["overthinking_score"] == 0.2
    assert loaded["context_health"] == 0.9
    assert loaded["verification_status"] == "ok"
    assert loaded["recommended_action"] == "continue"
    assert "updated_at" in loaded


def test_session_health_schema_required_fields() -> None:
    sv = schema_versions()["session_health"]
    for field in (
        "contamination_risk",
        "overthinking_score",
        "context_health",
        "verification_status",
        "recommended_action",
    ):
        assert field in sv["required_fields"], f"session_health missing required {field!r}"



def test_council_verdicts_write_read_round_trip(tmp_path: Path) -> None:
    payload = {
        "status": "ok",
        "verdicts": [{"check": "tests_pass", "result": "pass"}],
        "verification_status": "ok",
    }
    path = write_run_state(str(tmp_path), "council_verdicts", "run-cv1", payload)
    loaded = read_run_state(str(tmp_path), "council_verdicts", "run-cv1")

    assert Path(path).exists()
    assert loaded is not None
    assert loaded["schema"] == "CouncilVerdicts"
    assert loaded["schema_version"] == "1.0.0"
    assert loaded["run_id"] == "run-cv1"
    assert loaded["status"] == "ok"
    assert loaded["verdicts"] == [{"check": "tests_pass", "result": "pass"}]
    assert loaded["verification_status"] == "ok"
    assert "updated_at" in loaded


def test_council_verdicts_schema_required_fields() -> None:
    sv = schema_versions()["council_verdicts"]
    for field in ("verdicts", "verification_status"):
        assert field in sv["required_fields"], f"council_verdicts missing required {field!r}"



def test_rollback_manifest_write_read_round_trip(tmp_path: Path) -> None:
    payload = {
        "status": "ok",
        "step_id": "step-001",
        "local_restores": [{"file_path": "foo.py", "status": "restored"}],
        "compensating_actions": [],
        "side_effects": [],
    }
    path = write_run_state(str(tmp_path), "rollback_manifest", "run-rb1", payload)
    loaded = read_run_state(str(tmp_path), "rollback_manifest", "run-rb1")

    assert Path(path).exists()
    assert loaded is not None
    assert loaded["schema"] == "RollbackManifest"
    assert loaded["schema_version"] == "1.0.0"
    assert loaded["run_id"] == "run-rb1"
    assert loaded["status"] == "ok"
    assert loaded["step_id"] == "step-001"
    assert loaded["local_restores"] == [{"file_path": "foo.py", "status": "restored"}]
    assert loaded["compensating_actions"] == []
    assert loaded["side_effects"] == []
    assert "updated_at" in loaded


def test_rollback_manifest_schema_required_fields() -> None:
    sv = schema_versions()["rollback_manifest"]
    for field in ("step_id", "local_restores", "compensating_actions", "side_effects"):
        assert field in sv["required_fields"], f"rollback_manifest missing required {field!r}"



def test_release_run_write_read_round_trip(tmp_path: Path) -> None:
    payload = {
        "status": "running",
        "phase": "begin",
        "resolution_source": "cli",
        "resolution_reason": "resolved_from_cli",
        "release_evidence": {},
        "health_action": "continue",
    }
    path = write_run_state(str(tmp_path), "release_run", "run-rr1", payload)
    loaded = read_run_state(str(tmp_path), "release_run", "run-rr1")

    assert Path(path).exists()
    assert loaded is not None
    assert loaded["schema"] == "ReleaseRunState"
    assert loaded["schema_version"] == "1.0.0"
    assert loaded["run_id"] == "run-rr1"
    assert loaded["status"] == "running"
    assert loaded["phase"] == "begin"
    assert loaded["resolution_source"] == "cli"
    assert loaded["resolution_reason"] == "resolved_from_cli"
    assert loaded["release_evidence"] == {}
    assert loaded["health_action"] == "continue"
    assert "updated_at" in loaded


def test_release_run_schema_required_fields() -> None:
    sv = schema_versions()["release_run"]
    for field in ("phase", "resolution_source", "resolution_reason", "release_evidence", "health_action"):
        assert field in sv["required_fields"], f"release_run missing required {field!r}"



def test_unsupported_module_write_raises_value_error(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported state module"):
        write_run_state(str(tmp_path), "totally_bogus_module", "run-x", {"status": "ok"})


def test_unsupported_module_make_run_path_raises_value_error(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported state module"):
        make_run_path(str(tmp_path), "nonexistent_module_xyz", "run-x")


def test_unsupported_module_read_returns_none_not_crash(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported state module"):
        read_run_state(str(tmp_path), "fake_module", "run-x")



def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    _ = write_run_state(str(tmp_path), "session_health", "run-atom", {"status": "ok", "contamination_risk": 0.0, "overthinking_score": 0.0, "context_health": 1.0, "verification_status": "ok", "recommended_action": "continue"})
    state_dir = tmp_path / ".omg" / "state" / "session_health"
    tmp_files = list(state_dir.glob("*.tmp"))
    assert tmp_files == [], f"leftover .tmp files: {tmp_files}"


def test_all_new_modules_produce_valid_json(tmp_path: Path) -> None:
    test_cases = {
        "session_health": {"status": "ok", "contamination_risk": 0.0, "overthinking_score": 0.0, "context_health": 1.0, "verification_status": "ok", "recommended_action": "continue"},
        "council_verdicts": {"status": "ok", "verdicts": [], "verification_status": "ok"},
        "rollback_manifest": {"status": "ok", "step_id": "s1", "local_restores": [], "compensating_actions": [], "side_effects": []},
        "release_run": {"status": "running", "phase": "begin", "resolution_source": "generated", "resolution_reason": "generated_new_run_id", "release_evidence": {}, "health_action": "continue"},
    }
    for module, payload in test_cases.items():
        path_str = write_run_state(str(tmp_path), module, f"run-{module}", payload)
        raw = Path(path_str).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, dict), f"{module} did not produce a JSON object"
        assert parsed["schema_version"] == "1.0.0"
        assert parsed["run_id"] == f"run-{module}"
