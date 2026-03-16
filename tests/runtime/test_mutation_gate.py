from __future__ import annotations

from pathlib import Path

import pytest

from runtime.mutation_gate import check_mutation_allowed


def test_mutation_gate_read_only_bash_no_context_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="rg pattern .",
    )
    assert result["status"] == "allowed"
    assert result["reason"] == "tool is read-only for mutation gate"


def test_mutation_gate_mutation_bash_no_context_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="rm -rf foo",
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "mutation_context_required"


def test_mutation_gate_mutation_bash_with_context_no_lock_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    run_id = "run-context-no-lock"
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="rm -rf foo",
        run_id=run_id,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"
