from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.verification_controller import (
    VerificationController,
    auto_verify,
    enable_proof_by_default,
)


def test_begin_run_creates_run_scoped_state(tmp_path: Path) -> None:
    controller = VerificationController(str(tmp_path))

    state = controller.begin_run("run-begin")
    state_path = tmp_path / ".omg" / "state" / "verification_controller" / "run-begin.json"

    assert state_path.exists()
    assert state["run_id"] == "run-begin"
    assert state["status"] == "running"


def test_read_run_returns_not_found_for_missing_run(tmp_path: Path) -> None:
    controller = VerificationController(str(tmp_path))

    missing = controller.read_run("missing-run")

    assert missing == {"status": "not_found", "run_id": "missing-run"}


def test_publish_compat_state_writes_background_verification(tmp_path: Path) -> None:
    controller = VerificationController(str(tmp_path))
    _ = controller.begin_run("run-compat")

    compat_path = controller.publish_compat_state("run-compat")
    payload = cast(
        dict[str, object],
        json.loads((tmp_path / ".omg" / "state" / "background-verification.json").read_text(encoding="utf-8")),
    )

    assert compat_path.endswith(".omg/state/background-verification.json")
    assert payload["schema"] == "BackgroundVerificationState"
    assert payload["run_id"] == "run-compat"


def test_complete_run_updates_status(tmp_path: Path) -> None:
    controller = VerificationController(str(tmp_path))
    _ = controller.begin_run("run-complete")
    existing_evidence = tmp_path / ".omg" / "evidence" / "existing.json"
    existing_evidence.parent.mkdir(parents=True, exist_ok=True)
    existing_evidence.write_text('{"ok": true}', encoding="utf-8")

    completed = controller.complete_run(
        run_id="run-complete",
        status="ok",
        blockers=[],
        evidence_links=[".omg/evidence/existing.json"],
    )

    assert completed["run_id"] == "run-complete"
    assert completed["status"] == "ok"
    assert ".omg/evidence/existing.json" in completed["evidence_links"]
    assert ".omg/evidence/run-complete.json" in completed["evidence_links"]
    assert any(
        str(path).startswith(".omg/evidence/") and str(path).endswith("-auto.json")
        for path in completed["evidence_links"]
    )
    assert ".omg/evidence/proof-gate-run-complete.json" in completed["evidence_links"]
    auto_verification = cast(dict[str, object], completed["auto_verification"])
    assert auto_verification["evidence_path"]
    assert isinstance(auto_verification["proof_score"], int)


def test_enable_proof_by_default_writes_config(tmp_path: Path) -> None:
    enable_proof_by_default(str(tmp_path))

    config_path = tmp_path / ".omg" / "state" / "verification_controller" / "proof-by-default.json"
    payload = cast(dict[str, object], json.loads(config_path.read_text(encoding="utf-8")))

    assert payload["schema"] == "VerificationControllerAutoVerify"
    assert payload["enabled"] is True


def test_auto_verify_writes_evidence_and_proof_state(tmp_path: Path) -> None:
    seed_artifact = tmp_path / ".omg" / "evidence" / "seed.json"
    seed_artifact.parent.mkdir(parents=True, exist_ok=True)
    seed_artifact.write_text('{"schema": "seed"}', encoding="utf-8")

    result = auto_verify(
        {
            "run_id": "run-auto",
            "status": "ok",
            "evidence_links": [".omg/evidence/seed.json"],
        },
        str(tmp_path),
    )

    evidence_path = tmp_path / str(result["evidence_path"])
    compat_path = tmp_path / ".omg" / "evidence" / "run-auto.json"
    proof_state_path = tmp_path / ".omg" / "state" / "proof_gate" / "run-auto.json"

    assert result["evidence_path"].startswith(".omg/evidence/")
    assert str(result["evidence_path"]).endswith("-auto.json")
    assert evidence_path.exists()
    assert compat_path.exists()
    assert proof_state_path.exists()
    assert isinstance(result["proof_score"], int)
