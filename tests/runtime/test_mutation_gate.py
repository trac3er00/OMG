from __future__ import annotations
# pyright: reportMissingImports=false

from pathlib import Path

import pytest

from runtime.mutation_gate import (
    _is_allowlisted_read_only_command,
    _is_mutation_capable_bash,
    _strip_quoted_segments,
    check_mutation_allowed,
)


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


def test_mutation_gate_exemption_docs_allows_without_lock(tmp_path: Path) -> None:
    result = check_mutation_allowed(
        tool="Write",
        file_path="docs/guide.md",
        project_dir=str(tmp_path),
        lock_id=None,
        exemption="docs",
    )
    assert result["status"] == "exempt"
    assert "docs" in str(result["reason"])


def test_mutation_gate_metadata_exempt_allows_without_lock(tmp_path: Path) -> None:
    result = check_mutation_allowed(
        tool="Edit",
        file_path="src/code.py",
        project_dir=str(tmp_path),
        lock_id=None,
        exemption="config",
        metadata={"exempt": True, "exempt_reason": "bootstrap"},
    )
    assert result["status"] == "exempt"
    assert "metadata exemption" in str(result["reason"])


def test_mutation_gate_permissive_mode_allows_missing_context_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "0")
    with pytest.warns(RuntimeWarning, match="mutation_context_required"):
        result = check_mutation_allowed(
            tool="Write",
            file_path="src/new.py",
            project_dir=str(tmp_path),
            lock_id=None,
        )
    assert result["status"] == "allowed"
    assert result["reason"] == "mutation_context_required"


def test_mutation_gate_release_orchestration_bypasses_all_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("runtime.mutation_gate.is_release_orchestration_active", lambda project_dir: True)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=None,
        run_id="run-release",
    )
    assert result["status"] == "allowed"
    assert result["reason"] == "release_orchestration_active"


def test_mutation_gate_verify_lock_failure_blocks_in_strict_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    monkeypatch.setattr("runtime.mutation_gate.verify_lock", lambda *args, **kwargs: {"status": "error", "reason": "no_active_test_intent_lock"})
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/block.py",
        project_dir=str(tmp_path),
        lock_id="lock-1",
        run_id="run-1",
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"


def test_mutation_gate_verify_lock_failure_allows_in_permissive_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "0")
    monkeypatch.setattr("runtime.mutation_gate.verify_lock", lambda *args, **kwargs: {"status": "error", "reason": "missing_lock"})
    with pytest.warns(RuntimeWarning, match="missing_lock"):
        result = check_mutation_allowed(
            tool="Edit",
            file_path="src/allow.py",
            project_dir=str(tmp_path),
            lock_id="lock-x",
            run_id="run-x",
        )
    assert result["status"] == "allowed"
    assert result["reason"] == "missing_lock"


def test_mutation_gate_requires_tool_plan_when_lock_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    monkeypatch.setattr("runtime.mutation_gate.verify_lock", lambda *args, **kwargs: {"status": "ok", "lock_id": "lock-ok"})
    monkeypatch.setattr("runtime.mutation_gate.has_tool_plan_for_run", lambda project_dir, run_id: False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/needs-plan.py",
        project_dir=str(tmp_path),
        lock_id="lock-ok",
        run_id="run-plan",
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "tool_plan_required"


def test_mutation_gate_requires_done_when_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    monkeypatch.setattr("runtime.mutation_gate.verify_lock", lambda *args, **kwargs: {"status": "ok", "lock_id": "lock-ok"})
    monkeypatch.setattr("runtime.mutation_gate.has_tool_plan_for_run", lambda project_dir, run_id: True)
    monkeypatch.setattr("runtime.mutation_gate.verify_done_when", lambda metadata, run_id: {"status": "error", "reason": "done_when_required"})
    result = check_mutation_allowed(
        tool="Edit",
        file_path="src/needs-done-when.py",
        project_dir=str(tmp_path),
        lock_id="lock-ok",
        run_id="run-done-when",
        metadata={},
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "done_when_required"


def test_mutation_gate_allows_when_all_checks_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    monkeypatch.setattr("runtime.mutation_gate.verify_lock", lambda *args, **kwargs: {"status": "ok", "lock_id": "lock-good"})
    monkeypatch.setattr("runtime.mutation_gate.has_tool_plan_for_run", lambda project_dir, run_id: True)
    monkeypatch.setattr("runtime.mutation_gate.verify_done_when", lambda metadata, run_id: {"status": "ok"})
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/ok.py",
        project_dir=str(tmp_path),
        lock_id="lock-good",
        run_id="run-good",
        metadata={"done_when": "tests green"},
    )
    assert result["status"] == "allowed"
    assert result["reason"] == "active test intent lock found"
    assert result["lock_id"] == "lock-good"


def test_mutation_gate_detects_nested_shell_c_mutation() -> None:
    assert _is_mutation_capable_bash("bash -lc 'rm -rf build'") is True


def test_mutation_gate_treats_python_redirect_as_read_only() -> None:
    assert _is_mutation_capable_bash("python3 script.py > out.json") is False


def test_mutation_gate_detects_write_redirection_mutation() -> None:
    assert _is_mutation_capable_bash("echo hello > out.txt") is True


def test_mutation_gate_allows_tee_dev_null_pattern() -> None:
    assert _is_allowlisted_read_only_command("tee /dev/null") is True


def test_mutation_gate_strip_quoted_segments_fully_quoted_returns_empty() -> None:
    assert _strip_quoted_segments('"rm -rf /"') == ""
