"""Tests for UltraworkerRouter — high-level orchestration."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.mark.experimental
class TestUltraworkerFeatureGate:
    """Feature flag gating."""

    def test_init_raises_when_disabled(self, feature_flag_disabled):
        feature_flag_disabled("ULTRAWORKER")
        from claude_experimental.parallel.ultraworker import UltraworkerRouter

        with pytest.raises(RuntimeError, match="disabled"):
            UltraworkerRouter()


@pytest.mark.experimental
class TestUltraworkerRouter:
    """Core UltraworkerRouter operations with mocked executor."""

    @pytest.fixture(autouse=True)
    def _setup(self, feature_flag_enabled):
        feature_flag_enabled("ULTRAWORKER")
        feature_flag_enabled("PARALLEL_DISPATCH")

        self.mock_dispatcher = MagicMock()
        self._executor_patcher = patch(
            "claude_experimental.parallel.executor.ParallelExecutor._load_dispatcher",
            return_value=self.mock_dispatcher,
        )
        self._executor_patcher.start()
        from claude_experimental.parallel.ultraworker import UltraworkerRouter

        self.router = UltraworkerRouter(min_workers=1, max_workers=4)
        yield
        self.router.shutdown()
        self._executor_patcher.stop()

    def test_submit_returns_job_id(self):
        job_id = self.router.submit("test task", priority=2)
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_submit_increments_cost_units(self):
        self.router.submit("task 1")
        self.router.submit("task 2")
        stats = self.router.get_stats()
        assert stats["total_cost_units"] == 2

    def test_get_stats_keys(self):
        stats = self.router.get_stats()
        expected_keys = {"pool_size", "queued", "active", "completed", "total_cost_units"}
        assert set(stats.keys()) == expected_keys

    def test_get_stats_initial_values(self):
        stats = self.router.get_stats()
        assert stats["completed"] == 0
        assert stats["total_cost_units"] == 0
        assert stats["pool_size"] >= 1

    def test_shutdown_prevents_further_submit(self):
        self.router.shutdown()
        with pytest.raises(RuntimeError, match="shut down"):
            self.router.submit("task after shutdown")

    def test_shutdown_idempotent(self):
        """Calling shutdown twice should not raise."""
        self.router.shutdown()
        self.router.shutdown()  # no error

    def test_submit_batch_empty(self):
        job_ids = self.router.submit_batch([])
        assert job_ids == []

    def test_submit_with_custom_agent(self):
        self.mock_dispatcher.submit_job.return_value = "exec-001"
        job_id = self.router.submit(
            "custom task",
            agent_name="omg-architect",
            priority=5,
            batch_id="batch-1",
        )
        assert isinstance(job_id, str)
