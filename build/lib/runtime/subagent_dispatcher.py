"""Parallel Execution Backend — concurrent subagent job management.

Manages concurrent subagent jobs with isolation, artifact streaming,
and a 100-job limit using stdlib ThreadPoolExecutor.

Feature flag: OMG_PARALLEL_SUBAGENTS_ENABLED (default: False)
"""
from __future__ import annotations

import os
import sys
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

# --- Path resolution (never relies on CWD) ---
_DISPATCHER_DIR = os.path.dirname(os.path.abspath(__file__))
_OMG_ROOT = os.path.dirname(_DISPATCHER_DIR)

# --- Constants ---
MAX_JOBS = 100

# --- Module-level singletons ---
_executor: ThreadPoolExecutor | None = None
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _get_feature_flag() -> Any:
    """Lazy-import get_feature_flag from hooks/_common.py."""
    hooks_dir = os.path.join(_OMG_ROOT, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # pyright: ignore[reportMissingImports]
        return get_feature_flag
    except ImportError:
        return None


def _get_atomic_json_write() -> Any:
    """Lazy-import atomic_json_write from hooks/_common.py."""
    hooks_dir = os.path.join(_OMG_ROOT, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import atomic_json_write  # pyright: ignore[reportMissingImports]
        return atomic_json_write
    except ImportError:
        return None


def _is_enabled() -> bool:
    """Check if parallel subagents feature is enabled.

    Resolution: env var OMG_PARALLEL_SUBAGENTS_ENABLED → settings.json → default False.
    """
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_PARALLEL_SUBAGENTS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Slow path: check via get_feature_flag
    get_flag = _get_feature_flag()
    if get_flag is not None:
        return get_flag("PARALLEL_SUBAGENTS", default=False)
    return False


def _get_project_dir() -> str:
    """Get project directory from env or cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _jobs_dir() -> str:
    """Return the jobs state directory path."""
    return os.path.join(_get_project_dir(), ".omg", "state", "jobs")


def _job_path(job_id: str) -> str:
    """Return the file path for a specific job."""
    return os.path.join(_jobs_dir(), f"{job_id}.json")


def _persist_job(job_id: str, record: dict[str, Any]) -> None:
    """Persist job record to disk via atomic_json_write."""
    writer = _get_atomic_json_write()
    if writer is not None:
        writer(_job_path(job_id), record)


def _load_job_from_disk(job_id: str) -> dict[str, Any] | None:
    """Load a job record from disk if it exists."""
    path = _job_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get_executor() -> ThreadPoolExecutor:
    """Lazy-init and return the module-level ThreadPoolExecutor singleton."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_JOBS)
    return _executor


def _running_count() -> int:
    """Count jobs with status 'running'."""
    return len([j for j in _jobs.values() if j["status"] == "running"])


def submit_job(
    agent_name: str,
    task_text: str,
    isolation: str = "none",
) -> str:
    """Submit a subagent job for concurrent execution.

    Args:
        agent_name: Name of the agent to dispatch.
        task_text: Task description / prompt for the agent.
        isolation: Isolation backend — "none" (default) or "worktree".

    Returns:
        job_id (8-char hex string).

    Raises:
        RuntimeError: If feature is disabled or job limit reached.
    """
    if not _is_enabled():
        raise RuntimeError("feature disabled")

    with _lock:
        if _running_count() >= MAX_JOBS:
            raise RuntimeError("job limit reached")

        job_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "job_id": job_id,
            "agent_name": agent_name,
            "task_text": task_text,
            "isolation": isolation,
            "status": "queued",
            "created_at": now,
            "artifacts": [],
            "error": None,
        }
        _jobs[job_id] = record

    # Persist initial state
    _persist_job(job_id, record)

    # Submit to thread pool — returns immediately
    executor = get_executor()
    executor.submit(_run_job, job_id)

    return job_id


def _check_git_available() -> bool:
    """Return True if git is available on PATH."""
    import shutil
    return shutil.which("git") is not None


def _setup_worktree(job_id: str) -> str | None:
    """Attempt to create a git worktree for job isolation.

    Returns worktree path on success, None on failure.
    """
    if not _check_git_available():
        return None

    import subprocess

    project_dir = _get_project_dir()
    worktree_dir = os.path.join(project_dir, ".omg", "worktrees", job_id)

    try:
        os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "--detach", worktree_dir],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            cwd=project_dir,
        )
        return worktree_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def _cleanup_worktree(worktree_dir: str) -> None:
    """Remove a git worktree (best-effort)."""
    import subprocess
    import shutil

    project_dir = _get_project_dir()
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_dir],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            cwd=project_dir,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: remove directory if still exists
    try:
        if os.path.isdir(worktree_dir):
            shutil.rmtree(worktree_dir, ignore_errors=True)
    except OSError:
        pass


def _run_job(job_id: str) -> None:
    """Execute a subagent job in the thread pool.

    Updates job status and persists artifacts as they are produced.
    NOTE: Does NOT actually spawn Claude — simulates execution for now.
    """
    with _lock:
        record = _jobs.get(job_id)
        if record is None:
            return
        if record["status"] == "cancelled":
            return
        record["status"] = "running"
        record["started_at"] = datetime.now(timezone.utc).isoformat()

    _persist_job(job_id, record)

    worktree_dir: str | None = None
    try:
        # Setup isolation if requested
        if record.get("isolation") == "worktree":
            worktree_dir = _setup_worktree(job_id)
            if worktree_dir:
                with _lock:
                    record["worktree"] = worktree_dir
                _persist_job(job_id, record)

        # --- Simulated execution ---
        # Real implementation would dispatch to an agent here.
        # For now, simulate work + produce an artifact.
        time.sleep(0.05)  # Simulate brief work

        artifact = {
            "type": "result",
            "agent": record["agent_name"],
            "content": f"Simulated output for: {record['task_text'][:100]}",
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }

        with _lock:
            # Check for cancellation mid-execution
            if record["status"] == "cancelled":
                return
            record["artifacts"].append(artifact)
            record["status"] = "completed"
            record["completed_at"] = datetime.now(timezone.utc).isoformat()

        _persist_job(job_id, record)

    except Exception as exc:
        with _lock:
            record["status"] = "failed"
            record["error"] = str(exc)
            record["completed_at"] = datetime.now(timezone.utc).isoformat()
        _persist_job(job_id, record)

    finally:
        # Cleanup worktree if created
        if worktree_dir:
            _cleanup_worktree(worktree_dir)


def get_job_status(job_id: str) -> dict[str, Any]:
    """Get the current status and artifacts for a job.

    Args:
        job_id: Job identifier returned by submit_job().

    Returns:
        Job record dict, or {"error": "not found"} if job doesn't exist.
    """
    with _lock:
        record = _jobs.get(job_id)
        if record is not None:
            return dict(record)

    # Not in memory — try loading from disk
    disk_record = _load_job_from_disk(job_id)
    if disk_record is not None:
        return disk_record

    return {"error": "not found"}


def cancel_job(job_id: str) -> bool:
    """Cancel a queued or running job.

    Args:
        job_id: Job identifier to cancel.

    Returns:
        True if the job was cancelled, False if not found or already terminal.
    """
    with _lock:
        record = _jobs.get(job_id)
        if record is None:
            return False
        if record["status"] in ("completed", "failed", "cancelled"):
            return False
        record["status"] = "cancelled"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()

    _persist_job(job_id, record)
    return True


def list_jobs(status_filter: str | None = None) -> list[dict[str, Any]]:
    """List all jobs, optionally filtered by status.

    Args:
        status_filter: If provided, only return jobs matching this status.

    Returns:
        List of job record dicts.
    """
    with _lock:
        if status_filter is None:
            return [dict(j) for j in _jobs.values()]
        return [dict(j) for j in _jobs.values() if j["status"] == status_filter]


def shutdown(wait: bool = True) -> None:
    """Shut down the executor gracefully.

    Args:
        wait: If True, wait for running jobs to complete before returning.
    """
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=wait)
        _executor = None
