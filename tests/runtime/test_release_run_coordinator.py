from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from runtime.release_run_coordinator import ReleaseRunCoordinator, RunIdConflictError, build_release_env_prefix


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_happy_path_joins_run_id_across_lifecycle_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    coordinator = ReleaseRunCoordinator(str(tmp_path))
    begin_state = coordinator.begin(cli_run_id="run-flow")

    mutate_state = coordinator.mutate(
        run_id="run-flow",
        tool="write",
        metadata={"file": "README.md", "command": "write README.md"},
        goal="need docs and one security scan",
        available_tools=["context7", "omg_security_check"],
    )
    verify_state = coordinator.verify("run-flow")
    final_state = coordinator.finalize(
        run_id="run-flow",
        status="ok",
        blockers=[],
        evidence_links=[".omg/evidence/release-run.json"],
    )

    assert begin_state["run_id"] == "run-flow"
    assert mutate_state["run_id"] == "run-flow"
    assert verify_state["run_id"] == "run-flow"
    assert final_state["run_id"] == "run-flow"

    verification_state = _read_json(tmp_path / ".omg" / "state" / "verification_controller" / "run-flow.json")
    assert verification_state["run_id"] == "run-flow"
    assert verification_state["status"] == "ok"

    plans = sorted((tmp_path / ".omg" / "state" / "tool_plans").glob("*.json"))
    assert plans
    plan_payload = _read_json(plans[0])
    assert plan_payload["run_id"] == "run-flow"

    journal_entries = sorted((tmp_path / ".omg" / "state" / "interaction_journal").glob("*.json"))
    assert journal_entries
    latest_entry = _read_json(journal_entries[-1])
    metadata = latest_entry.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata["run_id"] == "run-flow"


def test_begin_prefers_cli_run_id_over_env_and_shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMG_RUN_ID", "run-env")
    active = tmp_path / ".omg" / "shadow" / "active-run"
    active.parent.mkdir(parents=True, exist_ok=True)
    _ = active.write_text("run-shadow\n", encoding="utf-8")

    coordinator = ReleaseRunCoordinator(str(tmp_path))
    state = coordinator.begin(cli_run_id="run-cli")

    assert state["run_id"] == "run-cli"
    assert active.read_text(encoding="utf-8").strip() == "run-cli"


def test_begin_in_strict_mode_rejects_fragmented_run_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMG_RUN_COORDINATOR_STRICT", "1")
    monkeypatch.setenv("OMG_RUN_ID", "run-env")
    active = tmp_path / ".omg" / "shadow" / "active-run"
    active.parent.mkdir(parents=True, exist_ok=True)
    _ = active.write_text("run-shadow\n", encoding="utf-8")

    coordinator = ReleaseRunCoordinator(str(tmp_path))

    with pytest.raises(RunIdConflictError) as exc:
        _ = coordinator.begin(cli_run_id="run-cli")

    assert "fragmented_run_ids" in str(exc.value)


def test_begin_in_permissive_mode_normalizes_fragmented_run_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMG_RUN_COORDINATOR_STRICT", raising=False)
    monkeypatch.setenv("OMG_RUN_ID", "run-env")
    active = tmp_path / ".omg" / "shadow" / "active-run"
    active.parent.mkdir(parents=True, exist_ok=True)
    _ = active.write_text("run-shadow\n", encoding="utf-8")

    coordinator = ReleaseRunCoordinator(str(tmp_path))
    state = coordinator.begin(cli_run_id="run-cli")

    assert state["run_id"] == "run-cli"
    assert state["resolution_reason"] == "fragmented_run_ids_normalized"


# ---------------------------------------------------------------------------
# build_release_env_prefix
# ---------------------------------------------------------------------------

class TestBuildReleaseEnvPrefix:
    def test_both_omg_vars_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
        monkeypatch.setenv("OMG_RUN_ID", "run-1")
        result = build_release_env_prefix("/proj")
        assert result == "env CLAUDE_PROJECT_DIR=/proj OMG_RELEASE_ORCHESTRATION_ACTIVE=1 OMG_RUN_ID=run-1 "

    def test_only_run_id_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", raising=False)
        monkeypatch.setenv("OMG_RUN_ID", "run-2")
        result = build_release_env_prefix("/proj")
        assert result == "env CLAUDE_PROJECT_DIR=/proj OMG_RUN_ID=run-2 "

    def test_neither_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", raising=False)
        monkeypatch.delenv("OMG_RUN_ID", raising=False)
        result = build_release_env_prefix("/proj")
        assert result == "env CLAUDE_PROJECT_DIR=/proj "

    def test_special_chars_quoted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
        monkeypatch.setenv("OMG_RUN_ID", "run;rm -rf /")
        result = build_release_env_prefix("/my project")
        assert "CLAUDE_PROJECT_DIR='/my project'" in result
        assert "OMG_RUN_ID='run;rm -rf /'" in result
        assert result.endswith(" ")
