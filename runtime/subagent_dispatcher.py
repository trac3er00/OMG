"""Parallel Execution Backend — concurrent subagent job management.

Manages concurrent subagent jobs with isolation, artifact streaming,
and a 100-job limit using stdlib ThreadPoolExecutor.

Feature flag: OMG_PARALLEL_SUBAGENTS_ENABLED (default: False)
"""
from __future__ import annotations

import os
import json
import logging
import shlex
import subprocess
import sys
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
_logger = logging.getLogger(__name__)


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


def resolve_execution_boundary(*, isolation: str = "worktree") -> dict[str, Any]:
    normalized = isolation.strip().lower() if isolation else "none"
    if normalized == "worktree":
        return {
            "sandbox_mode": "ephemeral_worktree",
            "worker_policy": os.environ.get("OMG_WORKER_POLICY", "managed-local"),
            "execution_mode": "local_supervisor",
        }
    if normalized == "container":
        return {
            "sandbox_mode": "container-like",
            "worker_policy": os.environ.get("OMG_WORKER_POLICY", "managed-local"),
            "execution_mode": "automation",
        }
    return {
        "sandbox_mode": "none",
        "worker_policy": "local-only",
        "execution_mode": "automation",
    }


def resolve_isolation_contract(*, isolation: str) -> dict[str, Any]:
    normalized = isolation.strip().lower() if isolation else "none"
    if normalized == "worktree":
        return {
            "requested": "worktree",
            "effective": "worktree",
            "status": "supported",
            "read_only": False,
            "boundary": resolve_execution_boundary(isolation="worktree"),
        }
    if normalized == "container":
        return {
            "requested": "container",
            "effective": "none",
            "status": "deferred",
            "reason": "container isolation is deferred/unsupported",
            "read_only": True,
            "boundary": resolve_execution_boundary(isolation="container"),
        }
    return {
        "requested": "none",
        "effective": "none",
        "status": "read-only",
        "reason": "none isolation permits read-only execution",
        "read_only": True,
        "boundary": resolve_execution_boundary(isolation="none"),
    }


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
    run_id: str | None = None,
    evidence_hooks: list[str] | None = None,
    attach_log: str | None = None,
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
        isolation_contract = resolve_isolation_contract(isolation=isolation)
        record: dict[str, Any] = {
            "job_id": job_id,
            "run_id": run_id,
            "agent_name": agent_name,
            "task_text": task_text,
            "isolation": isolation,
            "isolation_contract": isolation_contract,
            "status": "queued",
            "created_at": now,
            "artifacts": [],
            "evidence_hooks": list(evidence_hooks or []),
            "attach_log": attach_log,
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


def _write_job_evidence(job_id: str, payload: dict[str, Any], *, project_dir: str) -> str:
    evidence_dir = os.path.join(project_dir, ".omg", "evidence", "subagents")
    os.makedirs(evidence_dir, exist_ok=True)
    out_path = os.path.join(evidence_dir, f"{job_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return out_path


def _run_configured_worker(command_text: str, prompt: str, *, project_dir: str, worker: str) -> dict[str, Any]:
    command_text = command_text.strip()
    if not command_text:
        return {"status": "error", "worker": worker, "message": "worker command not configured"}

    if "{prompt}" in command_text or "{project_dir}" in command_text:
        try:
            cmd = [
                token.format(prompt=prompt, project_dir=project_dir)
                for token in shlex.split(command_text)
            ]
        except (ValueError, KeyError) as exc:
            return {"status": "error", "worker": worker, "message": f"invalid worker command template: {exc}"}
    else:
        cmd = shlex.split(command_text) + [prompt]
    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "worker": worker,
            "output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "worker": worker, "message": f"{worker} worker timed out"}
    except OSError as exc:
        return {"status": "error", "worker": worker, "message": str(exc)}


def _dispatch_job_task(record: dict[str, Any], *, project_dir: str) -> dict[str, Any]:
    runner_mode = os.environ.get("OMG_SUBAGENT_RUNNER", "").strip().lower()
    if runner_mode == "stub":
        return {
            "status": "ok",
            "worker": os.environ.get("OMG_SUBAGENT_STUB_WORKER", "stub"),
            "output": os.environ.get("OMG_SUBAGENT_STUB_OUTPUT", record["task_text"]),
            "exit_code": 0,
        }

    if runner_mode == "claude":
        return _run_configured_worker(
            os.environ.get("OMG_CLAUDE_WORKER_CMD", ""),
            record["task_text"],
            project_dir=project_dir,
            worker="claude",
        )

    from runtime.team_router import dispatch_to_model

    dispatched = dispatch_to_model(str(record["agent_name"]), str(record["task_text"]), project_dir)
    if "output" in dispatched or "exit_code" in dispatched:
        worker = str(dispatched.get("model", "unknown")).replace("-cli", "")
        return {
            "status": "ok" if int(dispatched.get("exit_code", 0) or 0) == 0 else "error",
            "worker": worker,
            "output": str(dispatched.get("output", "")),
            "exit_code": int(dispatched.get("exit_code", 0) or 0),
        }

    if dispatched.get("fallback") == "claude":
        return _run_configured_worker(
            os.environ.get("OMG_CLAUDE_WORKER_CMD", ""),
            record["task_text"],
            project_dir=project_dir,
            worker="claude",
        )

    return {
        "status": "error",
        "worker": str(dispatched.get("fallback", "unknown")),
        "message": str(dispatched.get("error", "worker unavailable")),
    }


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
        cleanup_proc = subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_dir],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            cwd=project_dir,
        )
        if cleanup_proc.returncode != 0:
            snippet = (cleanup_proc.stderr or cleanup_proc.stdout or "").strip()[:200]
            _logger.warning(
                "git worktree remove failed (rc=%d): %s",
                cleanup_proc.returncode,
                snippet,
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _logger.debug("Failed to remove git worktree during cleanup: %s", exc, exc_info=True)

    # Fallback: remove directory if still exists
    try:
        if os.path.isdir(worktree_dir):
            shutil.rmtree(worktree_dir, ignore_errors=True)
    except OSError as exc:
        _logger.debug("Failed to remove worktree directory during cleanup: %s", exc, exc_info=True)


def _enforce_merge_writer_gate(run_id: str, record: dict[str, Any], project_dir: str) -> None:
    try:
        from runtime.merge_writer import get_merge_writer, MergeWriterAuthorizationError
    except ImportError:
        # Optional: runtime.merge_writer not available
        return
    try:
        get_merge_writer(project_dir).require_authorization(
            run_id,
            mutation_type="worker_dispatch",
            isolation=str(record.get("isolation", "none")),
        )
    except MergeWriterAuthorizationError:
        raise
    except Exception as exc:
        _logger.debug("Failed to enforce merge writer gate: %s", exc, exc_info=True)


def _run_job(job_id: str) -> None:
    """Execute a subagent job in the thread pool.

    Updates job status, dispatches to a local worker, and persists artifacts/evidence.
    """
    with _lock:
        record = _jobs.get(job_id)
        if record is None:
            return
        if record["status"] == "cancelled":
            return
        record["status"] = "running"
        record["started_at"] = datetime.now(timezone.utc).isoformat()
        record["worker_pid"] = os.getpid()

    _persist_job(job_id, record)

    run_id = record.get("run_id") or job_id
    try:
        from runtime.worker_watchdog import get_worker_watchdog
        get_worker_watchdog(_get_project_dir()).record_heartbeat(
            run_id, worker_pid=os.getpid(),
        )
    except Exception as exc:
        _logger.debug("Failed to record worker heartbeat: %s", exc, exc_info=True)

    worktree_dir: str | None = None
    project_dir = _get_project_dir()
    try:
        if record.get("isolation") == "worktree":
            _enforce_merge_writer_gate(run_id, record, project_dir)

        # Setup isolation if requested
        if record.get("isolation") == "worktree":
            worktree_dir = _setup_worktree(job_id)
            if worktree_dir:
                with _lock:
                    record["worktree"] = worktree_dir
                _persist_job(job_id, record)

        active_project_dir = worktree_dir or project_dir
        dispatch_result = _dispatch_job_task(record, project_dir=active_project_dir)
        if dispatch_result.get("status") != "ok":
            raise RuntimeError(str(dispatch_result.get("message", "worker dispatch failed")))

        artifact = {
            "type": "worker-result",
            "agent": record["agent_name"],
            "worker": dispatch_result.get("worker", "unknown"),
            "exit_code": dispatch_result.get("exit_code", 0),
            "output": dispatch_result.get("output", ""),
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }
        evidence_payload = {
            "schema": "OmgSubagentEvidence",
            "job_id": job_id,
            "run_id": record.get("run_id"),
            "agent_name": record["agent_name"],
            "task_text": record["task_text"],
            "worker": dispatch_result.get("worker", "unknown"),
            "exit_code": dispatch_result.get("exit_code", 0),
            "output": dispatch_result.get("output", ""),
            "isolation_contract": record.get("isolation_contract", {}),
            "evidence_hooks": list(record.get("evidence_hooks", [])),
            "attach_log": record.get("attach_log"),
            "worktree": worktree_dir,
            "project_dir": active_project_dir,
        }
        evidence_path = _write_job_evidence(job_id, evidence_payload, project_dir=project_dir)
        artifact["evidence_path"] = os.path.relpath(evidence_path, project_dir)

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
    """Cancel a queued or running job, terminating the subprocess if running.

    Performs real subprocess termination (SIGTERM then SIGKILL after timeout),
    records terminal evidence, and cleans up stale worktrees.

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
        was_running = record["status"] == "running"
        record["status"] = "cancelled"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()

    run_id = record.get("run_id") or job_id
    worker_pid = record.get("worker_pid")
    worktree = record.get("worktree")

    try:
        from runtime.worker_watchdog import get_worker_watchdog
        watchdog = get_worker_watchdog(_get_project_dir())

        termination = None
        if worker_pid is not None and was_running:
            termination = watchdog.terminate_worker(run_id, worker_pid)

        cleanup = None
        if worktree:
            cleanup = watchdog.cleanup_stale_worktree(run_id)

        watchdog.emit_replay_evidence(
            run_id,
            f"cancel_job:{job_id}",
            termination=termination,
            cleanup=cleanup,
        )

        project_dir = _get_project_dir()
        cancel_evidence: dict[str, Any] = {
            "schema": "OmgSubagentCancelEvidence",
            "job_id": job_id,
            "run_id": run_id,
            "agent_name": record.get("agent_name", ""),
            "cancelled_at": record["completed_at"],
            "was_running": was_running,
            "worker_pid": worker_pid,
            "termination": termination,
            "cleanup": cleanup,
        }
        _write_job_evidence(job_id, cancel_evidence, project_dir=project_dir)
    except Exception as exc:
        _logger.debug("Failed to emit cancel evidence for subagent job: %s", exc, exc_info=True)

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
