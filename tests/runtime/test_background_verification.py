"""Tests for runtime.background_verification — canonical background verification state pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_publish_verification_state_writes_correct_state_file(tmp_path: Path) -> None:
    """Happy path: publish_verification_state writes .omg/state/background-verification.json with correct schema."""
    from runtime.background_verification import publish_verification_state

    result = publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-abc123",
        status="running",
        blockers=["proof_chain_missing_trace_id"],
        evidence_links=[".omg/evidence/security-check.json"],
        progress={"step": 2, "total": 5},
    )

    state_path = tmp_path / ".omg" / "state" / "background-verification.json"
    assert state_path.exists(), "State file must be created"
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert state["schema"] == "BackgroundVerificationState"
    assert state["schema_version"] == 2
    assert state["run_id"] == "run-abc123"
    assert state["status"] == "running"
    assert state["blockers"] == ["proof_chain_missing_trace_id"]
    assert state["evidence_links"] == [".omg/evidence/security-check.json"]
    assert state["progress"] == {"step": 2, "total": 5}
    assert "updated_at" in state

    assert result == str(state_path)


def test_publish_verification_state_ok_status(tmp_path: Path) -> None:
    """Verify all valid status values are accepted."""
    from runtime.background_verification import publish_verification_state

    for status in ("running", "ok", "error", "blocked"):
        publish_verification_state(
            project_dir=str(tmp_path),
            run_id=f"run-{status}",
            status=status,
            blockers=[],
            evidence_links=[],
            progress={},
        )
        state_path = tmp_path / ".omg" / "state" / "background-verification.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == status


def test_publish_verification_state_overwrites_stale_file(tmp_path: Path) -> None:
    """Stale state file is overwritten with new state."""
    from runtime.background_verification import publish_verification_state

    publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-old",
        status="running",
        blockers=[],
        evidence_links=[],
        progress={"step": 1, "total": 3},
    )
    publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-new",
        status="ok",
        blockers=[],
        evidence_links=[".omg/evidence/final.json"],
        progress={"step": 3, "total": 3},
    )

    state_path = tmp_path / ".omg" / "state" / "background-verification.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["run_id"] == "run-new"
    assert state["status"] == "ok"


def test_publish_verification_state_creates_missing_directories(tmp_path: Path) -> None:
    """State directory is created when missing."""
    from runtime.background_verification import publish_verification_state

    state_dir = tmp_path / ".omg" / "state"
    assert not state_dir.exists()

    publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-init",
        status="running",
        blockers=[],
        evidence_links=[],
        progress={},
    )

    assert state_dir.exists()
    assert (state_dir / "background-verification.json").exists()


def test_read_verification_state_degrades_gracefully_when_missing(tmp_path: Path) -> None:
    """Reading state when no file exists returns None or empty default."""
    from runtime.background_verification import read_verification_state

    result = read_verification_state(str(tmp_path))
    assert result is None


def test_read_verification_state_degrades_gracefully_on_corrupt_file(tmp_path: Path) -> None:
    """Reading corrupt state file returns None."""
    from runtime.background_verification import read_verification_state

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "background-verification.json").write_text("NOT JSON", encoding="utf-8")

    result = read_verification_state(str(tmp_path))
    assert result is None


def test_state_file_has_schema_version_2(tmp_path: Path) -> None:
    """Schema version must be exactly 2."""
    from runtime.background_verification import publish_verification_state

    publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-v2",
        status="ok",
        blockers=[],
        evidence_links=[],
        progress={},
    )

    state_path = tmp_path / ".omg" / "state" / "background-verification.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
