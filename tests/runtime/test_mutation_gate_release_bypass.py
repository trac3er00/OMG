from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.mutation_gate import check_mutation_allowed


def test_release_mode_blocks_test_intent_lock_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")

    with patch(
        "runtime.mutation_gate.is_release_orchestration_active", return_value=True
    ):
        with patch("runtime.mutation_gate.verify_lock") as mock_lock:
            mock_lock.return_value = {"status": "locked", "reason": "lock_active"}
            result = check_mutation_allowed(
                tool="Write",
                file_path="src/foo.py",
                project_dir=str(tmp_path),
                lock_id="test-lock-123",
            )

    reason = str(result.get("reason") or "")
    assert result["status"] == "blocked", f"Expected blocked but got: {result}"
    assert "lock" in reason.lower() or "test_intent" in reason.lower()


def test_release_mode_allows_done_when_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")

    with patch(
        "runtime.mutation_gate.is_release_orchestration_active", return_value=True
    ):
        with patch("runtime.mutation_gate.verify_lock") as mock_lock:
            with patch("runtime.mutation_gate.has_tool_plan_for_run") as mock_plan:
                with patch("runtime.mutation_gate.verify_done_when") as mock_done_when:
                    mock_lock.return_value = {"status": "ok"}
                    mock_plan.return_value = True
                    mock_done_when.return_value = {
                        "status": "pending",
                        "reason": "done_when_not_met",
                    }
                    result = check_mutation_allowed(
                        tool="Write",
                        file_path="src/foo.py",
                        project_dir=str(tmp_path),
                        lock_id="test-lock-123",
                    )

    reason = str(result.get("reason") or "")
    assert result["status"] == "allowed"
    assert "release" in reason.lower() or result.get("status") == "allowed"
