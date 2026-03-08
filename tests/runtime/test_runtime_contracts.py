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
