"""ParallelExecutor — high-level wrapper around subagent_dispatcher for Tier-1 parallel dispatch."""
from __future__ import annotations
import os
import sys
import time
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


JobRecord = dict[str, Any]
TaskSpec = dict[str, Any]


class ParallelExecutor:
    """High-level executor wrapping runtime/subagent_dispatcher.py for parallel agent dispatch.

    Usage:
        executor = ParallelExecutor()
        job_id = executor.submit("explore", "list files in current directory")
        result = executor.wait(job_id, timeout=60)
    """

    def __init__(self, isolation: str = "thread"):
        """Initialize executor.

        Args:
            isolation: 'thread' (ThreadPoolExecutor, default) or 'process' (future: sandbox)
        """
        self.isolation = isolation
        self._dispatcher = self._load_dispatcher()

    def _load_dispatcher(self) -> Any:
        """Lazy-load subagent_dispatcher via the canonical ``runtime`` package path.

        Using ``import runtime.subagent_dispatcher`` (not a bare ``import subagent_dispatcher``)
        guarantees that executor.py and all other callers share the same module object —
        and therefore the same ``_jobs`` dict, ``_executor`` singleton, and ``_dynamic_pool``.
        A bare import after ``sys.path.insert(runtime_dir)`` would register the module as
        ``subagent_dispatcher`` in sys.modules, splitting singletons from ``runtime.subagent_dispatcher``.
        """
        if _PROJECT_ROOT not in sys.path:
            sys.path.insert(0, _PROJECT_ROOT)
        try:
            import runtime.subagent_dispatcher as _mod  # pyright: ignore[reportMissingImports]
            return _mod
        except ImportError as e:
            raise ImportError(f"Cannot load subagent_dispatcher: {e}")

    def submit(self, agent_name: str, prompt: str, timeout: int = 300, isolation: str | None = None) -> str:
        """Submit a job for parallel dispatch.

        Returns:
            job_id: str
        """
        from claude_experimental._flags import get_feature_flag
        if not get_feature_flag("PARALLEL_DISPATCH", default=False):
            raise RuntimeError(
                "Tier-1 parallel dispatch is disabled. "
                "Enable with: OMG_PARALLEL_DISPATCH_ENABLED=1"
            )
        job_id = self._dispatcher.submit_job(
            agent_name=agent_name,
            task_text=prompt,
            isolation=isolation or self.isolation,
            timeout=timeout,
        )
        return job_id

    def status(self, job_id: str) -> JobRecord:
        """Get job status."""
        return self._dispatcher.get_job_status(job_id)

    def wait(self, job_id: str, timeout: int = 300, poll_interval: float = 0.5) -> JobRecord:
        """Wait for job to complete and return its record.

        Raises:
            TimeoutError: if job doesn't complete within timeout seconds
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            record = self.status(job_id)
            if record["status"] in ("completed", "failed", "cancelled"):
                return record
            time.sleep(poll_interval)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        return self._dispatcher.cancel_job(job_id)

    def submit_many(self, tasks: list[TaskSpec]) -> list[str]:
        """Submit multiple tasks and return list of job_ids.

        Args:
            tasks: list of {"agent_name": str, "prompt": str, "timeout": int}
        """
        return [
            self.submit(
                agent_name=t["agent_name"],
                prompt=t["prompt"],
                timeout=t.get("timeout", 300),
            )
            for t in tasks
        ]

    def wait_all(self, job_ids: list[str], timeout: int = 600) -> list[JobRecord]:
        """Wait for all jobs to complete. Returns list of job records."""
        deadline = time.time() + timeout
        results = []
        for job_id in job_ids:
            remaining = max(0, deadline - time.time())
            results.append(self.wait(job_id, timeout=int(remaining) + 1))
        return results
