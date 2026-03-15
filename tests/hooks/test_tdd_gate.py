from __future__ import annotations

import json
from hashlib import sha256

from runtime.mutation_gate import check_mutation_allowed


def test_mutation_gate_blocks_without_lock_in_strict_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"
    assert result["lock_id"] is None


def test_mutation_blocks_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    run_id = "run-missing-lock"
    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-min.json").write_text("{}", encoding="utf-8")

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
        run_id=run_id,
        metadata={"done_when": ["tests pass"]},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"


def test_mutation_gate_allows_docs_exemption_without_lock(tmp_path) -> None:
    result = check_mutation_allowed(
        tool="Write",
        file_path="docs/notes.md",
        project_dir=str(tmp_path),
        lock_id=None,
        exemption="docs",
    )
    assert result["status"] == "exempt"


def test_docs_exemption_passes(tmp_path) -> None:
    result = check_mutation_allowed(
        tool="Write",
        file_path="docs/notes.md",
        project_dir=str(tmp_path),
        lock_id=None,
        exemption="docs",
    )

    assert result["status"] == "exempt"


def test_mutation_gate_allows_with_valid_lock_id(tmp_path) -> None:
    lock_id = "lock-123"
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text("{}", encoding="utf-8")

    result = check_mutation_allowed(
        tool="Edit",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
    )
    assert result["status"] == "allowed"
    assert result["lock_id"] == lock_id


def _setup_release_orchestration_fixture(tmp_path, run_id="run-release", lock_id="lock-release"):
    """Seed shadow active-run, lock, and tool plan for a release orchestration scenario."""
    shadow_dir = tmp_path / ".omg" / "shadow"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "active-run").write_text(f"{run_id}\n", encoding="utf-8")

    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text(
        json.dumps({"lock_id": lock_id, "intent": {"run_id": run_id}}),
        encoding="utf-8",
    )

    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-release.json").write_text("{}", encoding="utf-8")


def test_release_orchestration_dual_signal_allows_without_done_when(tmp_path, monkeypatch) -> None:
    """Both active run AND env flag set → done_when check is skipped."""
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
    run_id = "run-release"
    lock_id = "lock-release"
    _setup_release_orchestration_fixture(tmp_path, run_id=run_id, lock_id=lock_id)

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=run_id,
        metadata={},
    )
    assert result["status"] == "allowed"
    assert result["reason"] == "release_orchestration_active"
    assert result["lock_id"] == lock_id


def test_release_orchestration_env_only_blocks_done_when(tmp_path, monkeypatch) -> None:
    """Env flag set but NO active run → gate still blocks with done_when_required."""
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
    run_id = "run-env-only"
    lock_id = "lock-env-only"

    # Set up lock + plan but NO shadow active-run file
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text(
        json.dumps({"lock_id": lock_id, "intent": {"run_id": run_id}}),
        encoding="utf-8",
    )

    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-release.json").write_text("{}", encoding="utf-8")

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=run_id,
        metadata={"done_when": ""},
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "done_when_required"


def test_release_orchestration_active_run_only_blocks_done_when(tmp_path, monkeypatch) -> None:
    """Active run exists but env flag NOT set → gate still blocks with done_when_required."""
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    monkeypatch.delenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", raising=False)
    run_id = "run-active-only"
    lock_id = "lock-active-only"
    _setup_release_orchestration_fixture(tmp_path, run_id=run_id, lock_id=lock_id)

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=run_id,
        metadata={"done_when": ""},
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "done_when_required"


def test_mutation_gate_does_not_block_read_only_tools(tmp_path) -> None:
    result = check_mutation_allowed(
        tool="Read",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "allowed"


def test_mutation_gate_blocks_without_lock_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"


def test_mutation_gate_writes_block_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    file_path = "src/app.py"
    result = check_mutation_allowed(
        tool="MultiEdit",
        file_path=file_path,
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"

    path_hash = sha256(file_path.encode("utf-8")).hexdigest()[:8]
    artifact_path = tmp_path / ".omg" / "state" / "mutation_gate" / f"{path_hash}.json"
    assert artifact_path.is_file()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["tool"] == "MultiEdit"
    assert payload["file_path"] == file_path
    assert isinstance(payload.get("reason"), str)
    assert isinstance(payload.get("ts"), str)


def test_mutation_gate_blocks_mutating_bash_without_lock_in_strict_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="touch runtime/new_file.py",
        run_id="run-123",
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"


def test_mutation_gate_allows_read_only_bash_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="git status",
        run_id="run-123",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_python_version_check_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="python -V",
        run_id="run-python-version",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_gh_pr_view_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="gh pr view 123",
        run_id="run-gh-pr-view",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_fully_quoted_literal_command(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command='"mkdir should-not-trigger"',
        run_id="run-quoted-literal",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_tee_dev_null_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="printf done | tee /dev/null",
        run_id="run-tee-dev-null",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_read_only_bash_with_discard_redirection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="ls /tmp 2>/dev/null",
        run_id="run-redirect-readonly",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_read_only_bash_with_fd_duplication(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="which rg >/dev/null 2>&1",
        run_id="run-fd-dup",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_still_blocks_real_file_redirection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="echo done > build.log",
        run_id="run-real-write",
    )
    assert result["status"] == "blocked"


def test_mutation_gate_still_blocks_shell_c_mutation_without_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command='bash -lc "touch runtime/real_mutation.txt"',
        run_id="run-shell-c-mutation",
    )
    assert result["status"] == "blocked"


def test_mutation_gate_allows_explicit_exempt_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
        metadata={"exempt": True, "exempt_reason": "trusted automation flow"},
    )
    assert result["status"] == "exempt"


def test_mutation_gate_demotes_exempt_without_reason(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
        metadata={"exempt": True},
    )
    assert result["status"] == "blocked"


def test_mutation_gate_exempt_with_exemption_category(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="docs/readme.md",
        project_dir=str(tmp_path),
        lock_id=None,
        exemption="docs",
        metadata={"exempt": True},
    )
    assert result["status"] == "exempt"


def test_mutation_gate_writes_block_artifact_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    file_path = "src/warn_target.py"
    result = check_mutation_allowed(
        tool="Write",
        file_path=file_path,
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"

    path_hash = sha256(file_path.encode("utf-8")).hexdigest()[:8]
    artifact_path = tmp_path / ".omg" / "state" / "mutation_gate" / f"{path_hash}.json"
    assert artifact_path.is_file()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["tool"] == "Write"
    assert payload["file_path"] == file_path
    assert isinstance(payload.get("reason"), str)
    assert isinstance(payload.get("ts"), str)


def test_mutation_gate_blocks_without_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    run_id = "run-no-plan"
    lock_id = "lock-no-plan"
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text(
        json.dumps({"lock_id": lock_id, "intent": {"run_id": run_id}}),
        encoding="utf-8",
    )

    result = check_mutation_allowed(
        tool="Edit",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=run_id,
        metadata={"done_when": ["all checks green"]},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "tool_plan_required"


def test_mutation_gate_blocks_without_done_when(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    run_id = "run-no-done-when"
    lock_id = "lock-no-done-when"
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text(
        json.dumps({"lock_id": lock_id, "intent": {"run_id": run_id}}),
        encoding="utf-8",
    )
    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-min.json").write_text("{}", encoding="utf-8")

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=run_id,
        metadata={"done_when": ""},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "done_when_required"


def test_mutation_gate_binds_to_active_coordinator_run_id(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    active_run_id = "run-active"
    mismatched_run_id = "run-metadata"
    shadow_dir = tmp_path / ".omg" / "shadow"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "active-run").write_text(f"{active_run_id}\n", encoding="utf-8")

    lock_id = "lock-active"
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / f"{lock_id}.json").write_text(
        json.dumps({"lock_id": lock_id, "intent": {"run_id": active_run_id}}),
        encoding="utf-8",
    )

    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{active_run_id}-plan-min.json").write_text("{}", encoding="utf-8")

    result = check_mutation_allowed(
        tool="Write",
        file_path="src/main.py",
        project_dir=str(tmp_path),
        lock_id=lock_id,
        run_id=mismatched_run_id,
        metadata={"done_when": ["tests pass"]},
    )

    assert result["status"] == "allowed"
    assert result["lock_id"] == lock_id
