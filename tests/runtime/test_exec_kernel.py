from __future__ import annotations

import json
from pathlib import Path

from runtime.exec_kernel import ExecKernel
from runtime.merge_writer import MergeWriter


def test_kernel_wraps_isolated_worker_run_worktree(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "true")

    captured: dict[str, object] = {}

    def _fake_submit_job(agent_name: str, task_text: str, **kwargs: object) -> str:
        captured["agent_name"] = agent_name
        captured["task_text"] = task_text
        captured.update(kwargs)
        return "job-worktree"

    import runtime.subagent_dispatcher as dispatcher

    monkeypatch.setattr(dispatcher, "submit_job", _fake_submit_job)

    kernel = ExecKernel(str(tmp_path))
    result = kernel.submit_worker(
        run_id="run-worktree",
        agent_name="backend-engineer",
        task_text="stabilize auth",
        isolation_mode="worktree",
        evidence_hooks=[".omg/evidence/subagents"],
    )

    assert result["status"] == "queued"
    assert result["isolation"]["effective"] == "worktree"
    assert result["kernel_enabled"] is True
    assert captured["run_id"] == "run-worktree"
    assert captured["isolation"] == "worktree"
    assert captured["attach_log"] == ".omg/state/exec-kernel/run-worktree.log"


def test_container_isolation_reports_deferred_unsupported(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "true")
    kernel = ExecKernel(str(tmp_path))

    result = kernel.submit_worker(
        run_id="run-container",
        agent_name="backend-engineer",
        task_text="stabilize auth",
        isolation_mode="container",
    )

    assert result["status"] == "deferred"
    assert result["job_id"] is None
    assert result["isolation"]["requested"] == "container"
    assert result["isolation"]["status"] == "deferred"
    assert "unsupported" in str(result["reason"])


def test_kernel_disabled_is_passthrough(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "false")

    def _fake_submit_job(_agent_name: str, _task_text: str, **_kwargs: object) -> str:
        return "job-passthrough"

    import runtime.subagent_dispatcher as dispatcher

    monkeypatch.setattr(dispatcher, "submit_job", _fake_submit_job)

    kernel = ExecKernel(str(tmp_path))
    result = kernel.submit_worker(
        run_id="run-disabled",
        agent_name="backend-engineer",
        task_text="stabilize auth",
        isolation_mode="none",
    )

    assert result["status"] == "queued"
    assert result["passthrough"] is True
    assert result["kernel_enabled"] is False
    assert result["job_id"] == "job-passthrough"


def test_run_state_is_persisted_and_retrievable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "true")
    kernel = ExecKernel(str(tmp_path))

    run = kernel.register_run("run-state", isolation_mode="none", source="test")
    state = kernel.get_run_state(run.run_id)

    state_path = tmp_path / ".omg" / "state" / "exec-kernel" / "run-state.json"
    assert state_path.exists()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert state["run_id"] == "run-state"
    assert state["attach_log"] == ".omg/state/exec-kernel/run-state.log"
    assert persisted["kernel_run"]["run_id"] == "run-state"
    assert persisted["isolation"]["status"] == "read-only"


def test_register_run_without_id_uses_active_coordinator_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "true")
    active_run_path = tmp_path / ".omg" / "shadow" / "active-run"
    active_run_path.parent.mkdir(parents=True, exist_ok=True)
    active_run_path.write_text("coord-run\n", encoding="utf-8")

    kernel = ExecKernel(str(tmp_path))
    run = kernel.register_run(None, isolation_mode="worktree", source="test")

    assert run.run_id == "coord-run"
    state = kernel.get_run_state("coord-run")
    assert state["run_id"] == "coord-run"


def test_submit_worker_records_run_and_merge_writer_ownership(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_EXEC_KERNEL_ENABLED", "true")
    active_run_path = tmp_path / ".omg" / "shadow" / "active-run"
    active_run_path.parent.mkdir(parents=True, exist_ok=True)
    active_run_path.write_text("run-ownership\n", encoding="utf-8")

    merge_writer = MergeWriter(str(tmp_path))
    merge_writer.acquire("run-ownership", reason="ownership test")

    captured: dict[str, object] = {}

    def _fake_submit_job(agent_name: str, task_text: str, **kwargs: object) -> str:
        captured["agent_name"] = agent_name
        captured["task_text"] = task_text
        captured.update(kwargs)
        return "job-ownership"

    import runtime.subagent_dispatcher as dispatcher

    monkeypatch.setattr(dispatcher, "submit_job", _fake_submit_job)

    kernel = ExecKernel(str(tmp_path))
    result = kernel.submit_worker(
        run_id="run-ownership",
        agent_name="backend-engineer",
        task_text="govern merge",
        isolation_mode="worktree",
    )

    assert result["status"] == "queued"
    assert result["run_id"] == "run-ownership"
    assert result["ownership"]["active_run_id"] == "run-ownership"
    assert result["ownership"]["merge_writer"]["owner_run_id"] == "run-ownership"
    assert result["ownership"]["merge_writer"]["authorized"] is True

    state = kernel.get_run_state("run-ownership")
    assert state["ownership"]["active_run_id"] == "run-ownership"
    assert state["ownership"]["merge_writer"]["authorized"] is True
