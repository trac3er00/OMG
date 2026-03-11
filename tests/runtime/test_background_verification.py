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


# --- Task 10: Smart validation skipping + progress state ---


def test_should_skip_validation_true_for_docs_only_profile() -> None:
    """docs-only profile skips non-essential validations like build/tests."""
    from runtime.background_verification import should_skip_validation

    assert should_skip_validation("docs-only", "build") is True
    assert should_skip_validation("docs-only", "tests") is True
    assert should_skip_validation("docs-only", "security_scan") is True


def test_should_skip_validation_false_for_docs_only_required() -> None:
    """docs-only profile does NOT skip its own requirements (lsp_clean, trace_link)."""
    from runtime.background_verification import should_skip_validation

    assert should_skip_validation("docs-only", "lsp_clean") is False
    assert should_skip_validation("docs-only", "trace_link") is False


def test_should_skip_validation_never_for_release_profile() -> None:
    """release profile must NEVER skip any validation stage."""
    from runtime.background_verification import should_skip_validation

    for stage in ["tests", "lsp_clean", "build", "provenance", "trust_scores",
                  "security_scan", "license_scan", "sbom", "trace_link"]:
        assert should_skip_validation("release", stage) is False, f"release must not skip {stage}"


def test_should_skip_validation_never_for_security_audit_profile() -> None:
    """security-audit profile must NEVER skip any validation stage."""
    from runtime.background_verification import should_skip_validation

    for stage in ["tests", "lsp_clean", "build", "provenance", "trust_scores",
                  "security_scan", "license_scan", "sbom", "trace_link"]:
        assert should_skip_validation("security-audit", stage) is False, f"security-audit must not skip {stage}"


def test_should_skip_validation_forge_run_skips_non_required() -> None:
    """forge-run profile skips stages not in its requirements."""
    from runtime.background_verification import should_skip_validation

    assert should_skip_validation("forge-run", "build") is True
    assert should_skip_validation("forge-run", "security_scan") is True
    assert should_skip_validation("forge-run", "tests") is False
    assert should_skip_validation("forge-run", "lsp_clean") is False


def test_should_skip_validation_unknown_profile_skips_nothing() -> None:
    """Unknown/missing profile falls back to full requirements — skips nothing."""
    from runtime.background_verification import should_skip_validation

    assert should_skip_validation(None, "tests") is False
    assert should_skip_validation("", "build") is False
    assert should_skip_validation("unknown-profile", "lsp_clean") is False


def test_publish_verification_state_includes_step_total_in_progress(tmp_path: Path) -> None:
    """Progress state must include step and total fields for HUD consumption."""
    from runtime.background_verification import publish_verification_state

    result = publish_verification_state(
        project_dir=str(tmp_path),
        run_id="run-progress",
        status="running",
        blockers=[],
        evidence_links=[],
        progress={"step": 3, "total": 7, "current_stage": "lsp_clean"},
    )

    state_path = tmp_path / ".omg" / "state" / "background-verification.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["progress"]["step"] == 3
    assert state["progress"]["total"] == 7
    assert state["progress"]["current_stage"] == "lsp_clean"


def test_run_validation_with_timeout_completes_within_limit(tmp_path: Path) -> None:
    """Validation with timeout gate completes for fast operations."""
    from runtime.background_verification import run_validation_with_timeout

    def fast_check() -> str:
        return "ok"

    result = run_validation_with_timeout(fast_check, timeout_seconds=5)
    assert result["status"] == "ok"
    assert result["timed_out"] is False


def test_run_validation_with_timeout_marks_timeout(tmp_path: Path) -> None:
    """Validation that exceeds timeout is marked as timed_out."""
    import time
    from runtime.background_verification import run_validation_with_timeout

    def slow_check() -> str:
        time.sleep(3)
        return "ok"

    result = run_validation_with_timeout(slow_check, timeout_seconds=0.5)
    assert result["timed_out"] is True
    assert result["status"] == "timeout"


def test_skipped_stages_list_for_docs_only() -> None:
    """skipped_stages_for_profile returns the correct stages to skip for docs-only."""
    from runtime.background_verification import skipped_stages_for_profile

    skipped = skipped_stages_for_profile("docs-only")
    assert "build" in skipped
    assert "tests" in skipped
    assert "lsp_clean" not in skipped
    assert "trace_link" not in skipped


def test_new_evidence_profiles_registered() -> None:
    """Verify new evidence profiles are registered in EVIDENCE_REQUIREMENTS_BY_PROFILE."""
    from runtime.evidence_requirements import EVIDENCE_REQUIREMENTS_BY_PROFILE

    new_profiles = [
        "browser-flow",
        "forge-cybersecurity",
        "interop-diagnosis",
        "install-validation",
        "buffet",
    ]
    for profile in new_profiles:
        assert profile in EVIDENCE_REQUIREMENTS_BY_PROFILE, f"Profile {profile} not registered"


def test_new_evidence_profiles_resolve_correctly() -> None:
    """Verify requirements_for_profile returns specific requirements for new profiles."""
    from runtime.evidence_requirements import requirements_for_profile

    # browser-flow should likely require trace_link and maybe some browser-specific evidence
    browser_reqs = requirements_for_profile("browser-flow")
    assert "trace_link" in browser_reqs

    # forge-cybersecurity should require security_scan and artifact_contracts
    forge_sec_reqs = requirements_for_profile("forge-cybersecurity")
    assert "security_scan" in forge_sec_reqs
    assert "artifact_contracts" in forge_sec_reqs

    # interop-diagnosis should require trust_scores and provenance
    interop_reqs = requirements_for_profile("interop-diagnosis")
    assert "trust_scores" in interop_reqs
    assert "provenance" in interop_reqs

    # install-validation should require tests and build
    install_reqs = requirements_for_profile("install-validation")
    assert "tests" in install_reqs
    assert "build" in install_reqs

    # buffet should probably require everything (full requirements)
    buffet_reqs = requirements_for_profile("buffet")
    from runtime.evidence_requirements import FULL_REQUIREMENTS
    assert set(buffet_reqs) == set(FULL_REQUIREMENTS)
