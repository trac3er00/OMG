"""Tests for parallel execution backend / subagent dispatcher (Task 2.5)."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from unittest.mock import patch, MagicMock, call

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOOKS_DIR = os.path.join(_ROOT, "hooks")
_RUNTIME_DIR = os.path.join(_ROOT, "runtime")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)

from runtime.subagent_dispatcher import (
    MAX_JOBS,
    _is_enabled,
    _jobs,
    _lock,
    _persist_job,
    _load_job_from_disk,
    _running_count,
    submit_job,
    get_job_status,
    cancel_job,
    list_jobs,
    get_executor,
    shutdown,
    _run_job,
    _run_configured_worker,
    _check_git_available,
)


# --- Helpers ---

def _clear_jobs():
    """Clear in-memory job registry between tests."""
    with _lock:
        _jobs.clear()


@pytest.fixture(autouse=True)
def clean_jobs():
    """Reset job registry before and after each test."""
    _clear_jobs()
    yield
    _clear_jobs()


# =============================================================================
# Test: Feature Flag
# =============================================================================


class TestFeatureFlag:
    """Tests for OMG_PARALLEL_SUBAGENTS_ENABLED feature flag."""

    def test_disabled_by_default(self):
        """Feature should be disabled when env var is not set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if it exists
            os.environ.pop("OMG_PARALLEL_SUBAGENTS_ENABLED", None)
            with patch("runtime.subagent_dispatcher._get_feature_flag", return_value=None):
                assert _is_enabled() is False

    def test_enabled_via_env_var(self):
        """Feature enabled when env var is '1'."""
        with patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"}):
            assert _is_enabled() is True

    def test_disabled_via_env_var_false(self):
        """Feature disabled when env var is 'false'."""
        with patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "false"}):
            assert _is_enabled() is False

    def test_submit_raises_when_disabled(self):
        """submit_job should raise RuntimeError when feature is disabled."""
        with patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "0"}):
            with pytest.raises(RuntimeError, match="feature disabled"):
                submit_job("test-agent", "do something")


# =============================================================================
# Test: Constants
# =============================================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_max_jobs_is_100(self):
        """MAX_JOBS should be 100."""
        assert MAX_JOBS == 100


# =============================================================================
# Test: Submit Job
# =============================================================================


class TestSubmitJob:
    """Tests for submit_job() function."""

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_returns_job_id(self, mock_executor, mock_persist):
        """submit_job should return an 8-char hex job_id."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("test-agent", "run tests")

        assert isinstance(job_id, str)
        assert len(job_id) == 8
        # Verify it's valid hex
        int(job_id, 16)

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_job_record_created(self, mock_executor, mock_persist):
        """submit_job should create a job record in _jobs."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("my-agent", "fix bug #42")

        assert job_id in _jobs
        record = _jobs[job_id]
        assert record["agent_name"] == "my-agent"
        assert record["task_text"] == "fix bug #42"
        assert record["status"] == "queued"
        assert record["isolation"] == "none"
        assert record["artifacts"] == []
        assert record["error"] is None

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_job_persisted_to_disk(self, mock_executor, mock_persist):
        """submit_job should call _persist_job with the record."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("agent-x", "task y")

        mock_persist.assert_called()
        call_args = mock_persist.call_args
        assert call_args[0][0] == job_id

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_submit_with_worktree_isolation(self, mock_executor, mock_persist):
        """submit_job should accept isolation='worktree'."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("agent", "task", isolation="worktree")

        record = _jobs[job_id]
        assert record["isolation"] == "worktree"

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_executor_submit_called(self, mock_executor, mock_persist):
        """submit_job should submit _run_job to the executor."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("agent", "task")

        mock_pool.submit.assert_called_once()
        call_args = mock_pool.submit.call_args
        assert call_args[0][0] == _run_job
        assert call_args[0][1] == job_id


# =============================================================================
# Test: Job Limit Enforcement
# =============================================================================


class TestJobLimit:
    """Tests for 100 concurrent job limit enforcement."""

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_limit_enforced(self, mock_executor, mock_persist):
        """submit_job should raise when 100 running jobs exist."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        # Pre-populate with MAX_JOBS running jobs
        for i in range(MAX_JOBS):
            _jobs[f"fake{i:04d}"] = {"status": "running"}

        with pytest.raises(RuntimeError, match="job limit reached"):
            submit_job("agent", "task")

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_completed_jobs_dont_count(self, mock_executor, mock_persist):
        """Completed jobs should not count toward the limit."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        # Pre-populate with MAX_JOBS completed jobs
        for i in range(MAX_JOBS):
            _jobs[f"done{i:04d}"] = {"status": "completed"}

        # Should succeed — no running jobs
        job_id = submit_job("agent", "task")
        assert isinstance(job_id, str)

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_limit_counts_only_running(self, mock_executor, mock_persist):
        """Only running jobs count toward the limit."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        # 99 running + 50 completed = still under limit
        for i in range(99):
            _jobs[f"run{i:04d}"] = {"status": "running"}
        for i in range(50):
            _jobs[f"done{i:04d}"] = {"status": "completed"}

        # Should succeed — only 99 running
        job_id = submit_job("agent", "task")
        assert isinstance(job_id, str)


# =============================================================================
# Test: Get Job Status
# =============================================================================


class TestGetJobStatus:
    """Tests for get_job_status() function."""

    def test_not_found(self):
        """get_job_status should return error dict for unknown job_id."""
        result = get_job_status("nonexistent")
        assert result == {"error": "not found"}

    @patch("runtime.subagent_dispatcher._persist_job")
    @patch("runtime.subagent_dispatcher.get_executor")
    @patch.dict(os.environ, {"OMG_PARALLEL_SUBAGENTS_ENABLED": "1"})
    def test_returns_job_record(self, mock_executor, mock_persist):
        """get_job_status should return the job record from memory."""
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool

        job_id = submit_job("my-agent", "check status")

        result = get_job_status(job_id)
        assert result["job_id"] == job_id
        assert result["agent_name"] == "my-agent"
        assert result["status"] == "queued"

    def test_loads_from_disk_fallback(self, tmp_path):
        """get_job_status should fall back to disk when not in memory."""
        # Create a job file on disk
        job_id = "abc12345"
        jobs_dir = tmp_path / ".omg" / "state" / "jobs"
        jobs_dir.mkdir(parents=True)
        job_file = jobs_dir / f"{job_id}.json"
        record = {"job_id": job_id, "status": "completed", "agent_name": "disk-agent"}
        job_file.write_text(json.dumps(record))

        with patch("runtime.subagent_dispatcher._get_project_dir", return_value=str(tmp_path)):
            result = get_job_status(job_id)
            assert result["job_id"] == job_id
            assert result["status"] == "completed"
            assert result["agent_name"] == "disk-agent"


# =============================================================================
# Test: Cancel Job
# =============================================================================


class TestCancelJob:
    """Tests for cancel_job() function."""

    def test_cancel_not_found(self):
        """cancel_job should return False for unknown job_id."""
        assert cancel_job("nonexistent") is False

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_queued_job(self, mock_persist):
        """cancel_job should cancel a queued job and return True."""
        _jobs["abc123"] = {"status": "queued", "job_id": "abc123"}

        result = cancel_job("abc123")

        assert result is True
        assert _jobs["abc123"]["status"] == "cancelled"

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_running_job(self, mock_persist):
        """cancel_job should cancel a running job and return True."""
        _jobs["run456"] = {"status": "running", "job_id": "run456"}

        result = cancel_job("run456")

        assert result is True
        assert _jobs["run456"]["status"] == "cancelled"

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_completed_job_returns_false(self, mock_persist):
        """cancel_job should return False for already-completed jobs."""
        _jobs["done789"] = {"status": "completed", "job_id": "done789"}

        result = cancel_job("done789")

        assert result is False
        assert _jobs["done789"]["status"] == "completed"

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_already_cancelled(self, mock_persist):
        """cancel_job should return False for already-cancelled jobs."""
        _jobs["can012"] = {"status": "cancelled", "job_id": "can012"}

        result = cancel_job("can012")

        assert result is False


# =============================================================================
# Test: List Jobs
# =============================================================================


class TestListJobs:
    """Tests for list_jobs() function."""

    def test_empty_list(self):
        """list_jobs should return empty list when no jobs exist."""
        assert list_jobs() == []

    def test_list_all_jobs(self):
        """list_jobs without filter returns all jobs."""
        _jobs["a"] = {"status": "running", "job_id": "a"}
        _jobs["b"] = {"status": "completed", "job_id": "b"}
        _jobs["c"] = {"status": "queued", "job_id": "c"}

        result = list_jobs()
        assert len(result) == 3

    def test_filter_by_status(self):
        """list_jobs with status_filter returns only matching jobs."""
        _jobs["a"] = {"status": "running", "job_id": "a"}
        _jobs["b"] = {"status": "completed", "job_id": "b"}
        _jobs["c"] = {"status": "running", "job_id": "c"}

        result = list_jobs(status_filter="running")
        assert len(result) == 2
        assert all(j["status"] == "running" for j in result)

    def test_filter_no_match(self):
        """list_jobs with non-matching filter returns empty list."""
        _jobs["a"] = {"status": "running", "job_id": "a"}

        result = list_jobs(status_filter="failed")
        assert result == []


# =============================================================================
# Test: Run Job (Simulated Execution)
# =============================================================================


class TestRunJob:
    """Tests for _run_job() function."""

    @patch("runtime.subagent_dispatcher._dispatch_job_task", return_value={
        "status": "ok",
        "worker": "codex",
        "exit_code": 0,
        "output": "{\"status\":\"ok\"}",
    })
    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_completes_job(self, mock_persist, mock_dispatch):
        """_run_job should transition job from queued → running → completed."""
        _jobs["test01"] = {
            "job_id": "test01",
            "agent_name": "test-agent",
            "task_text": "hello world",
            "isolation": "none",
            "status": "queued",
            "artifacts": [],
            "error": None,
        }

        _run_job("test01")

        mock_dispatch.assert_called_once()
        assert _jobs["test01"]["status"] == "completed"
        assert len(_jobs["test01"]["artifacts"]) == 1
        assert _jobs["test01"]["artifacts"][0]["type"] == "worker-result"

    @patch("runtime.subagent_dispatcher._dispatch_job_task", return_value={
        "status": "ok",
        "worker": "codex",
        "exit_code": 0,
        "output": "{\"status\":\"ok\"}",
    })
    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_records_worker_result_artifact(self, mock_persist, mock_dispatch):
        """_run_job should capture structured worker output instead of a simulated placeholder."""
        _jobs["real01"] = {
            "job_id": "real01",
            "agent_name": "backend-engineer",
            "task_text": "stabilize auth",
            "isolation": "none",
            "status": "queued",
            "artifacts": [],
            "error": None,
        }

        _run_job("real01")

        mock_dispatch.assert_called_once()
        artifact = _jobs["real01"]["artifacts"][0]
        assert artifact["type"] == "worker-result"
        assert artifact["worker"] == "codex"
        assert artifact["exit_code"] == 0

    @patch("runtime.subagent_dispatcher._dispatch_job_task", return_value={
        "status": "error",
        "worker": "claude",
        "message": "worker unavailable",
    })
    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_marks_job_failed_when_worker_dispatch_fails(self, mock_persist, mock_dispatch):
        """_run_job should fail the job when the worker dispatch returns an error payload."""
        _jobs["fail01"] = {
            "job_id": "fail01",
            "agent_name": "architect-mode",
            "task_text": "produce design",
            "isolation": "none",
            "status": "queued",
            "artifacts": [],
            "error": None,
        }

        _run_job("fail01")

        mock_dispatch.assert_called_once()
        assert _jobs["fail01"]["status"] == "failed"
        assert "worker unavailable" in (_jobs["fail01"]["error"] or "")

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_skips_cancelled_job(self, mock_persist):
        """_run_job should not execute an already-cancelled job."""
        _jobs["cancel1"] = {
            "job_id": "cancel1",
            "agent_name": "agent",
            "task_text": "task",
            "isolation": "none",
            "status": "cancelled",
            "artifacts": [],
            "error": None,
        }

        _run_job("cancel1")

        assert _jobs["cancel1"]["status"] == "cancelled"
        assert len(_jobs["cancel1"]["artifacts"]) == 0

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_missing_job(self, mock_persist):
        """_run_job should handle missing job_id gracefully."""
        # Should not raise
        _run_job("nonexistent")

    @patch("runtime.subagent_dispatcher._dispatch_job_task", return_value={
        "status": "ok",
        "worker": "codex",
        "exit_code": 0,
        "output": "{\"status\":\"ok\"}",
    })
    @patch("runtime.subagent_dispatcher._setup_worktree", return_value="/tmp/fake-worktree")
    @patch("runtime.subagent_dispatcher._cleanup_worktree")
    @patch("runtime.subagent_dispatcher._persist_job")
    def test_run_with_worktree_isolation(self, mock_persist, mock_cleanup, mock_setup, mock_dispatch):
        """_run_job should setup and cleanup worktree when isolation='worktree'."""
        _jobs["wt01"] = {
            "job_id": "wt01",
            "agent_name": "agent",
            "task_text": "task",
            "isolation": "worktree",
            "status": "queued",
            "artifacts": [],
            "error": None,
        }

        _run_job("wt01")

        mock_setup.assert_called_once_with("wt01")
        mock_dispatch.assert_called_once()
        mock_cleanup.assert_called_once_with("/tmp/fake-worktree")
        assert _jobs["wt01"]["status"] == "completed"
        assert _jobs["wt01"].get("worktree") == "/tmp/fake-worktree"


class TestConfiguredWorkerCommand:
    """Tests for configured worker command argument handling."""

    @patch("runtime.subagent_dispatcher.subprocess.run")
    def test_prompt_placeholder_stays_single_argv_entry(self, mock_run):
        """Prompt placeholders must remain a single argv item even when prompt contains spaces."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        _run_configured_worker(
            "claude --prompt {prompt} --cwd {project_dir}",
            "--unsafe flag with spaces",
            project_dir="/tmp/project",
            worker="claude",
        )

        cmd = mock_run.call_args.args[0]
        assert cmd == [
            "claude",
            "--prompt",
            "--unsafe flag with spaces",
            "--cwd",
            "/tmp/project",
        ]


# =============================================================================
# Test: Executor Management
# =============================================================================


class TestExecutor:
    """Tests for executor singleton management."""

    def test_get_executor_returns_pool(self):
        """get_executor should return a ThreadPoolExecutor."""
        import runtime.subagent_dispatcher as mod
        old_executor = mod._executor
        mod._executor = None  # Force re-creation
        try:
            pool = get_executor()
            assert isinstance(pool, ThreadPoolExecutor)
        finally:
            # Cleanup
            if mod._executor is not None:
                mod._executor.shutdown(wait=False)
            mod._executor = old_executor

    def test_shutdown_clears_executor(self):
        """shutdown should set _executor to None."""
        import runtime.subagent_dispatcher as mod
        old_executor = mod._executor
        mod._executor = MagicMock()
        try:
            shutdown(wait=False)
            assert mod._executor is None
        finally:
            mod._executor = old_executor


# =============================================================================
# Test: Git Check
# =============================================================================


class TestGitCheck:
    """Tests for git availability checking."""

    @patch("shutil.which", return_value="/usr/bin/git")
    def test_git_available(self, mock_which):
        """_check_git_available should return True when git is on PATH."""
        assert _check_git_available() is True

    @patch("shutil.which", return_value=None)
    def test_git_unavailable(self, mock_which):
        """_check_git_available should return False when git is missing."""
        assert _check_git_available() is False


# =============================================================================
# Test: Artifact Streaming
# =============================================================================


class TestArtifactStreaming:
    """Tests for artifact persistence to .omg/state/jobs/<job_id>.json."""

    def test_persist_calls_atomic_write(self):
        """_persist_job should call atomic_json_write with correct path."""
        mock_writer = MagicMock()
        with patch("runtime.subagent_dispatcher._get_atomic_json_write", return_value=mock_writer):
            with patch("runtime.subagent_dispatcher._get_project_dir", return_value="/proj"):
                record = {"job_id": "x1", "status": "running"}
                _persist_job("x1", record)

                mock_writer.assert_called_once_with(
                    "/proj/.omg/state/jobs/x1.json",
                    record,
                )

    def test_persist_handles_missing_writer(self):
        """_persist_job should not crash if atomic_json_write unavailable."""
        with patch("runtime.subagent_dispatcher._get_atomic_json_write", return_value=None):
            # Should not raise
            _persist_job("x2", {"job_id": "x2"})

    def test_load_from_disk(self, tmp_path):
        """_load_job_from_disk should read job file from disk."""
        jobs_dir = tmp_path / ".omg" / "state" / "jobs"
        jobs_dir.mkdir(parents=True)
        job_file = jobs_dir / "disk01.json"
        record = {"job_id": "disk01", "status": "completed"}
        job_file.write_text(json.dumps(record))

        with patch("runtime.subagent_dispatcher._get_project_dir", return_value=str(tmp_path)):
            result = _load_job_from_disk("disk01")
            assert result is not None
            assert result["job_id"] == "disk01"

    def test_load_from_disk_missing(self, tmp_path):
        """_load_job_from_disk should return None for missing file."""
        with patch("runtime.subagent_dispatcher._get_project_dir", return_value=str(tmp_path)):
            result = _load_job_from_disk("nope")
            assert result is None
