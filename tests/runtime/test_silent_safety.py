from __future__ import annotations

from pathlib import Path

import pytest

from runtime.mutation_gate import check_mutation_allowed


def _check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tool: str = "Write",
    file_path: str = "src/output.txt",
    command: str | None = None,
    exemption: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object | None]:
    monkeypatch.setenv("SILENT_SAFETY", "true")
    return check_mutation_allowed(
        tool=tool,
        file_path=file_path,
        project_dir=str(tmp_path),
        lock_id=None,
        exemption=exemption,
        command=command,
        run_id=run_id,
        metadata=metadata,
    )


def test_silent_mode_blocks_rm_rf_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="rm -rf build",
        command="rm -rf build",
    )
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_auto_approves_write_to_safe_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(tmp_path, monkeypatch, tool="Write", file_path="src/output.txt")
    assert result["status"] == "allowed"
    assert result["allowed"] is True
    assert result["silent"] is True


def test_silent_mode_blocks_dot_env_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(tmp_path, monkeypatch, tool="Write", file_path=".env")
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_blocks_force_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="git push --force origin main",
        command="git push --force origin main",
    )
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_auto_approves_npm_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="npm install",
        command="npm install",
    )
    assert result["status"] == "allowed"
    assert result["allowed"] is True
    assert result["silent"] is True


def test_normal_mode_write_still_requires_governance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SILENT_SAFETY", raising=False)
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    result = check_mutation_allowed(
        tool="Write",
        file_path="src/output.txt",
        project_dir=str(tmp_path),
        lock_id=None,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "mutation_context_required"
    assert result.get("silent") in (None, False)


def test_silent_mode_blocks_omg_path_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path, monkeypatch, tool="Write", file_path=".omg/state/lock.json"
    )
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_blocks_drop_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="DROP TABLE users",
        command="psql -c 'DROP TABLE users'",
    )
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_auto_approves_git_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="git commit -m test",
        command="git commit -m 'test'",
    )
    assert result["status"] == "allowed"
    assert result["allowed"] is True
    assert result["silent"] is True


def test_silent_mode_blocks_credentials_file_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path, monkeypatch, tool="Edit", file_path="config/credentials.json"
    )
    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert result["silent"] is False


def test_silent_mode_auto_approves_touch_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="touch notes.txt",
        command="touch notes.txt",
    )
    assert result["status"] == "allowed"
    assert result["allowed"] is True
    assert result["silent"] is True


def test_silent_mode_non_allowlisted_bash_still_uses_normal_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _check(
        tmp_path,
        monkeypatch,
        tool="Bash",
        file_path="git push origin main",
        command="git push origin main",
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "mutation_context_required"
    assert result.get("silent") in (None, False)
