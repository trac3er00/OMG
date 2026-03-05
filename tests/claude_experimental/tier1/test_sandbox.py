"""Tests for SandboxedExecutor — subprocess-based process isolation."""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.mark.experimental
class TestSandboxedExecutorFeatureGate:
    """Feature flag gating for SandboxedExecutor."""

    def test_init_raises_when_disabled(self, feature_flag_disabled):
        feature_flag_disabled("PARALLEL_DISPATCH")
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        with pytest.raises(RuntimeError, match="disabled"):
            SandboxedExecutor()


@pytest.mark.experimental
class TestSandboxedExecutorExecution:
    """Actual subprocess execution tests (real PIDs)."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PARALLEL_DISPATCH")

    def test_run_simple_code(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(job_fn_source="result = 2 + 3")
        assert result["exit_code"] == 0
        assert result["result"] == 5

    def test_pid_differs_from_parent(self):
        """Child subprocess must have a different PID."""
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(job_fn_source="result = __import__('os').getpid()")
        assert result["exit_code"] == 0
        assert result["pid"] != os.getpid()
        assert result["result"] != os.getpid()

    def test_args_passed_to_worker(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(
            job_fn_source="result = args['x'] * 2",
            args={"x": 21},
        )
        assert result["exit_code"] == 0
        assert result["result"] == 42

    def test_error_in_worker_captured(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(job_fn_source="raise ValueError('boom')")
        assert result["error"] is not None
        assert "ValueError" in result["error"]

    def test_timeout_enforcement(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(
            job_fn_source="import time; time.sleep(60); result = 'done'",
            timeout=1,
        )
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"].lower() or "timeout" in (result["error"] or "").lower()

    def test_run_many(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        jobs = [
            {"job_fn_source": "result = 1"},
            {"job_fn_source": "result = 2"},
        ]
        results = executor.run_many(jobs)
        assert len(results) == 2
        assert results[0]["result"] == 1
        assert results[1]["result"] == 2

    def test_duration_ms_populated(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(job_fn_source="result = 'fast'")
        assert isinstance(result["duration_ms"], float)
        assert result["duration_ms"] >= 0

    def test_schema_version_present(self):
        from claude_experimental.parallel.sandbox import SandboxedExecutor

        executor = SandboxedExecutor()
        result = executor.run(job_fn_source="result = None")
        assert result["schema_version"] == 1
