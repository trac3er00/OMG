"""Tests for ParallelExecutor — Tier-1 parallel dispatch."""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.mark.experimental
class TestParallelExecutorFeatureGate:
    """Feature flag gating for ParallelExecutor."""

    def test_submit_raises_when_disabled(self, feature_flag_disabled):
        """submit() must raise RuntimeError when PARALLEL_DISPATCH is off."""
        feature_flag_disabled("PARALLEL_DISPATCH")

        # Mock the dispatcher so __init__ doesn't fail on import
        with patch(
            "claude_experimental.parallel.executor.ParallelExecutor._load_dispatcher",
            return_value=MagicMock(),
        ):
            from claude_experimental.parallel.executor import ParallelExecutor

            executor = ParallelExecutor()
            with pytest.raises(RuntimeError, match="disabled"):
                executor.submit("explore", "test prompt")

    def test_submit_proceeds_when_enabled(self, feature_flag_enabled):
        """submit() succeeds when PARALLEL_DISPATCH is enabled."""
        feature_flag_enabled("PARALLEL_DISPATCH")

        mock_dispatcher = MagicMock()
        mock_dispatcher.submit_job.return_value = "job-001"

        with patch(
            "claude_experimental.parallel.executor.ParallelExecutor._load_dispatcher",
            return_value=mock_dispatcher,
        ):
            from claude_experimental.parallel.executor import ParallelExecutor

            executor = ParallelExecutor()
            job_id = executor.submit("explore", "list files")

        assert job_id == "job-001"
        mock_dispatcher.submit_job.assert_called_once_with(
            agent_name="explore",
            task_text="list files",
            isolation="thread",
        )


@pytest.mark.experimental
class TestParallelExecutorOperations:
    """Core operations with mocked dispatcher."""

    @pytest.fixture(autouse=True)
    def _setup(self, feature_flag_enabled):
        feature_flag_enabled("PARALLEL_DISPATCH")
        self.mock_dispatcher = MagicMock()
        self._patcher = patch(
            "claude_experimental.parallel.executor.ParallelExecutor._load_dispatcher",
            return_value=self.mock_dispatcher,
        )
        self._patcher.start()
        from claude_experimental.parallel.executor import ParallelExecutor

        self.executor = ParallelExecutor()
        yield
        self._patcher.stop()

    def test_status_delegates_to_dispatcher(self):
        self.mock_dispatcher.get_job_status.return_value = {
            "job_id": "j1",
            "status": "running",
        }
        result = self.executor.status("j1")
        assert result["status"] == "running"

    def test_cancel_delegates_to_dispatcher(self):
        self.mock_dispatcher.cancel_job.return_value = True
        assert self.executor.cancel("j1") is True

    def test_submit_many_returns_list_of_ids(self):
        self.mock_dispatcher.submit_job.side_effect = ["id-1", "id-2"]
        tasks = [
            {"agent_name": "a1", "prompt": "p1"},
            {"agent_name": "a2", "prompt": "p2"},
        ]
        ids = self.executor.submit_many(tasks)
        assert ids == ["id-1", "id-2"]

    def test_submit_many_empty_list(self):
        ids = self.executor.submit_many([])
        assert ids == []

    def test_wait_returns_completed_job(self):
        self.mock_dispatcher.get_job_status.return_value = {
            "job_id": "j1",
            "status": "completed",
        }
        result = self.executor.wait("j1", timeout=5)
        assert result["status"] == "completed"

    def test_wait_raises_timeout(self):
        self.mock_dispatcher.get_job_status.return_value = {
            "job_id": "j1",
            "status": "running",
        }
        with pytest.raises(TimeoutError, match="did not complete"):
            self.executor.wait("j1", timeout=0, poll_interval=0.01)

    def test_isolation_default_is_thread(self):
        assert self.executor.isolation == "thread"
