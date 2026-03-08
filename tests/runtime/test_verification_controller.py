from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.verification_controller import VerificationController


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

    completed = controller.complete_run(
        run_id="run-complete",
        status="ok",
        blockers=[],
        evidence_links=[".omg/evidence/run-complete.json"],
    )

    assert completed["run_id"] == "run-complete"
    assert completed["status"] == "ok"
    assert completed["evidence_links"] == [".omg/evidence/run-complete.json"]
