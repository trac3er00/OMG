from __future__ import annotations

import json
from hashlib import sha256

from runtime.mutation_gate import check_mutation_allowed


def test_mutation_gate_blocks_without_lock_in_strict_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "no_active_test_intent_lock"
    assert result["lock_id"] is None


def test_mutation_gate_allows_docs_exemption_without_lock(tmp_path) -> None:
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


def test_mutation_gate_does_not_block_read_only_tools(tmp_path) -> None:
    result = check_mutation_allowed(
        tool="Read",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "allowed"


def test_mutation_gate_warns_without_lock_when_not_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "allowed"
    assert result["reason"] == "no_active_test_intent_lock"


def test_mutation_gate_writes_block_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
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
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
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
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    result = check_mutation_allowed(
        tool="Bash",
        file_path=".",
        project_dir=str(tmp_path),
        lock_id=None,
        command="git status",
        run_id="run-123",
    )
    assert result["status"] == "allowed"


def test_mutation_gate_allows_explicit_exempt_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/app.py",
        project_dir=str(tmp_path),
        lock_id=None,
        metadata={"exempt": True},
    )
    assert result["status"] == "exempt"
