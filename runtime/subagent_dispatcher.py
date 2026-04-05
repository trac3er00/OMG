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


class AgentCoordinator:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._file_owners: dict[str, str] = {}
        self._job_agents: dict[str, str] = {}
        self._job_files: dict[str, set[str]] = {}

    def register_agent(self, *, job_id: str, agent_name: str) -> None:
        with self._lock:
            self._job_agents[job_id] = agent_name

    def clear(self) -> None:
        with self._lock:
            self._file_owners.clear()
            self._job_agents.clear()
            self._job_files.clear()

    def claim_files(self, *, job_id: str, files: list[str]) -> dict[str, Any]:
        normalized = sorted(
            {self._normalize_file_path(path) for path in files if str(path).strip()}
        )
        if not normalized:
            return {"allowed": True, "conflicts": [], "claimed": []}

        conflicts: list[dict[str, str]] = []
        with self._lock:
            agent_name = self._job_agents.get(job_id, "")
            for path in normalized:
                owner_job_id = self._file_owners.get(path)
                if owner_job_id and owner_job_id != job_id:
                    conflicts.append(
                        {
                            "file_path": path,
                            "owner_job_id": owner_job_id,
                            "owner_agent_name": self._job_agents.get(
                                owner_job_id, "unknown"
                            ),
                            "requesting_job_id": job_id,
                            "requesting_agent_name": agent_name or "unknown",
                        }
                    )

            if conflicts:
                return {"allowed": False, "conflicts": conflicts, "claimed": []}

            claimed = self._job_files.setdefault(job_id, set())
            for path in normalized:
                self._file_owners[path] = job_id
                claimed.add(path)
            return {"allowed": True, "conflicts": [], "claimed": normalized}

    def ownership_snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._file_owners)

    def _normalize_file_path(self, path: str) -> str:
        return str(path).strip().replace("\\", "/")


_agent_coordinator = AgentCoordinator()


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


def _to_positive_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _to_nonnegative_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _build_governed_context(
    job_id: str, record: dict[str, Any], *, project_dir: str
) -> dict[str, Any]:
    context_run_id = str(record.get("run_id") or job_id)
    lane_name = f"subagent-lane-{job_id}"

    envelope_path = os.path.join(
        project_dir, ".omg", "state", "budget-envelopes", f"{context_run_id}.json"
    )
    rollback_step_id = f"subagent-{job_id}"
    rollback_path = os.path.join(
        project_dir,
        ".omg",
        "state",
        "rollback_manifest",
        f"{context_run_id}-{rollback_step_id}.json",
    )

    return {
        "tool_fabric_lane": lane_name,
        "budget_envelope": {
            "run_id": context_run_id,
            "cpu_seconds_limit": _to_positive_float(
                os.environ.get("OMG_SUBAGENT_BUDGET_CPU_SECONDS"), 120.0
            ),
            "memory_mb_limit": _to_positive_float(
                os.environ.get("OMG_SUBAGENT_BUDGET_MEMORY_MB"), 2048.0
            ),
            "wall_time_seconds_limit": _to_positive_float(
                os.environ.get("OMG_SUBAGENT_BUDGET_WALL_SECONDS"), 600.0
            ),
            "token_limit": _to_nonnegative_int(
                os.environ.get("OMG_SUBAGENT_BUDGET_TOKENS"), 12000
            ),
            "network_bytes_limit": _to_nonnegative_int(
                os.environ.get("OMG_SUBAGENT_BUDGET_NETWORK_BYTES"), 0
            ),
            "state_path": envelope_path,
        },
        "rollback_manifest_path": rollback_path,
        "rollback_manifest_step_id": rollback_step_id,
    }


def _ensure_governed_context(
    job_id: str, record: dict[str, Any], *, project_dir: str
) -> dict[str, Any]:
    governed_context = record.get("governed_context")
    if not isinstance(governed_context, dict):
        governed_context = _build_governed_context(
            job_id, record, project_dir=project_dir
        )
        record["governed_context"] = governed_context

    budget_envelope = governed_context.get("budget_envelope")
    if isinstance(budget_envelope, dict):
        try:
            from runtime.budget_envelopes import get_budget_envelope_manager

            envelope_run_id = str(
                budget_envelope.get("run_id") or record.get("run_id") or job_id
            )
            manager = get_budget_envelope_manager(project_dir)
            if manager.get_envelope_state(envelope_run_id) is None:
                manager.create_envelope(
                    envelope_run_id,
                    cpu_seconds_limit=_to_positive_float(
                        budget_envelope.get("cpu_seconds_limit"), 120.0
                    ),
                    memory_mb_limit=_to_positive_float(
                        budget_envelope.get("memory_mb_limit"), 2048.0
                    ),
                    wall_time_seconds_limit=_to_positive_float(
                        budget_envelope.get("wall_time_seconds_limit"), 600.0
                    ),
                    token_limit=_to_nonnegative_int(
                        budget_envelope.get("token_limit"), 12000
                    ),
                    network_bytes_limit=_to_nonnegative_int(
                        budget_envelope.get("network_bytes_limit"), 0
                    ),
                )
        except Exception as exc:
            _logger.debug(
                "Failed to initialize budget envelope for %s: %s",
                job_id,
                exc,
                exc_info=True,
            )

    rollback_path = str(governed_context.get("rollback_manifest_path", "")).strip()
    if rollback_path and not os.path.exists(rollback_path):
        try:
            from runtime.rollback_manifest import (
                create_rollback_manifest,
                write_rollback_manifest,
            )

            manifest = create_rollback_manifest(
                str(record.get("run_id") or job_id),
                str(
                    governed_context.get("rollback_manifest_step_id")
                    or f"subagent-{job_id}"
                ),
            )
            materialized_path = write_rollback_manifest(project_dir, manifest)
            governed_context["rollback_manifest_path"] = materialized_path
        except Exception as exc:
            _logger.debug(
                "Failed to initialize rollback manifest for %s: %s",
                job_id,
                exc,
                exc_info=True,
            )

    return governed_context


def _extract_modified_files(
    dispatch_result: dict[str, Any], *, project_dir: str
) -> list[str]:
    raw_modified = dispatch_result.get("modified_files")
    if isinstance(raw_modified, list):
        return [
            str(path).strip().replace("\\", "/")
            for path in raw_modified
            if str(path).strip()
        ]

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc.returncode != 0:
            return []
        modified: list[str] = []
        for line in proc.stdout.splitlines():
            if not line.strip() or len(line) < 4:
                continue
            payload = line[3:].strip()
            if not payload:
                continue
            if " -> " in payload:
                payload = payload.split(" -> ", 1)[1].strip()
            normalized = payload.replace("\\", "/")
            if normalized:
                modified.append(normalized)
        return sorted(set(modified))
    except (OSError, subprocess.SubprocessError):
        return []


def _evaluate_conflict_policy(conflicts: list[dict[str, str]]) -> dict[str, str]:
    decision = (
        str(os.environ.get("OMG_MULTI_AGENT_CONFLICT_POLICY", "deny")).strip().lower()
    )
    if decision not in {"allow", "ask", "deny"}:
        decision = "deny"

    if decision == "allow":
        return {"decision": "allow", "reason": "policy allow"}
    if decision == "ask":
        return {"decision": "ask", "reason": "policy requires explicit operator review"}

    paths = ", ".join(
        sorted(
            {
                entry.get("file_path", "")
                for entry in conflicts
                if entry.get("file_path")
            }
        )
    )
    return {
        "decision": "deny",
        "reason": f"cross-agent file ownership conflict detected: {paths}"
        if paths
        else "cross-agent file ownership conflict detected",
    }


def _record_governed_usage(
    record: dict[str, Any],
    *,
    project_dir: str,
    wall_time_seconds: float,
    output_text: str,
) -> None:
    governed_context = record.get("governed_context")
    if not isinstance(governed_context, dict):
        return

    envelope = governed_context.get("budget_envelope")
    if not isinstance(envelope, dict):
        return

    try:
        from runtime.budget_envelopes import get_budget_envelope_manager

        run_id = str(
            envelope.get("run_id") or record.get("run_id") or record.get("job_id") or ""
        )
        if not run_id:
            return

        manager = get_budget_envelope_manager(project_dir)
        manager.record_usage(
            run_id,
            wall_time_seconds=max(0.0, wall_time_seconds),
            tokens=max(0, len(output_text) // 4),
        )
        check = manager.check_envelope(run_id)
        record["budget_check"] = {
            "status": check.status,
            "governance_action": check.governance_action,
            "reason": check.reason,
            "breached_dimensions": list(check.breached_dimensions),
        }
        if check.governance_action == "block":
            raise RuntimeError(f"budget envelope blocked execution: {check.reason}")
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        _logger.debug("Failed to record governed budget usage: %s", exc, exc_info=True)


def _record_rollback_side_effects(
    record: dict[str, Any], *, project_dir: str, modified_files: list[str]
) -> None:
    governed_context = record.get("governed_context")
    if not isinstance(governed_context, dict):
        return

    rollback_path = str(governed_context.get("rollback_manifest_path", "")).strip()
    if not rollback_path or not os.path.exists(rollback_path):
        return

    try:
        from runtime.rollback_manifest import (
            record_side_effect,
            write_rollback_manifest,
        )

        with open(rollback_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            return

        for file_path in modified_files:
            record_side_effect(
                manifest,
                {
                    "category": "local_file",
                    "decision": "reversible",
                    "reversible": True,
                    "reason": "subagent file mutation",
                    "file_path": file_path,
                },
            )
        materialized_path = write_rollback_manifest(project_dir, manifest)
        governed_context["rollback_manifest_path"] = materialized_path
    except Exception as exc:
        _logger.debug("Failed to record rollback side effects: %s", exc, exc_info=True)


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
        record["governed_context"] = _build_governed_context(
            job_id, record, project_dir=_get_project_dir()
        )
        _agent_coordinator.register_agent(job_id=job_id, agent_name=agent_name)
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


def _write_job_evidence(
    job_id: str, payload: dict[str, Any], *, project_dir: str
) -> str:
    evidence_dir = os.path.join(project_dir, ".omg", "evidence", "subagents")
    os.makedirs(evidence_dir, exist_ok=True)
    out_path = os.path.join(evidence_dir, f"{job_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return out_path


def _run_configured_worker(
    command_text: str, prompt: str, *, project_dir: str, worker: str
) -> dict[str, Any]:
    command_text = command_text.strip()
    if not command_text:
        return {
            "status": "error",
            "worker": worker,
            "message": "worker command not configured",
        }

    if "{prompt}" in command_text or "{project_dir}" in command_text:
        try:
            cmd = [
                token.format(prompt=prompt, project_dir=project_dir)
                for token in shlex.split(command_text)
            ]
        except (ValueError, KeyError) as exc:
            return {
                "status": "error",
                "worker": worker,
                "message": f"invalid worker command template: {exc}",
            }
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
        return {
            "status": "error",
            "worker": worker,
            "message": f"{worker} worker timed out",
        }
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

    dispatched = dispatch_to_model(
        str(record["agent_name"]), str(record["task_text"]), project_dir
    )
    if "output" in dispatched or "exit_code" in dispatched:
        worker = str(dispatched.get("model", "unknown")).replace("-cli", "")
        return {
            "status": "ok"
            if int(dispatched.get("exit_code", 0) or 0) == 0
            else "error",
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
        _logger.debug(
            "Failed to remove git worktree during cleanup: %s", exc, exc_info=True
        )

    # Fallback: remove directory if still exists
    try:
        if os.path.isdir(worktree_dir):
            shutil.rmtree(worktree_dir, ignore_errors=True)
    except OSError as exc:
        _logger.debug(
            "Failed to remove worktree directory during cleanup: %s", exc, exc_info=True
        )


def _enforce_merge_writer_gate(
    run_id: str, record: dict[str, Any], project_dir: str
) -> None:
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
            run_id,
            worker_pid=os.getpid(),
        )
    except Exception as exc:
        _logger.debug("Failed to record worker heartbeat: %s", exc, exc_info=True)

    worktree_dir: str | None = None
    project_dir = _get_project_dir()
    wall_time_start = datetime.now(timezone.utc)
    try:
        governed_context = _ensure_governed_context(
            job_id, record, project_dir=project_dir
        )
        _agent_coordinator.register_agent(
            job_id=job_id, agent_name=str(record.get("agent_name", ""))
        )

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
            raise RuntimeError(
                str(dispatch_result.get("message", "worker dispatch failed"))
            )

        modified_files = _extract_modified_files(
            dispatch_result, project_dir=active_project_dir
        )
        ownership = _agent_coordinator.claim_files(job_id=job_id, files=modified_files)
        conflict_decision: dict[str, str] | None = None
        if not ownership.get("allowed", True):
            conflicts = ownership.get("conflicts", [])
            conflict_decision = _evaluate_conflict_policy(
                conflicts if isinstance(conflicts, list) else []
            )
            record["conflict_gate"] = {
                "status": "fired",
                "decision": conflict_decision.get("decision", "deny"),
                "reason": conflict_decision.get("reason", "cross-agent conflict"),
                "conflicts": conflicts,
            }
            if conflict_decision.get("decision") != "allow":
                raise RuntimeError(
                    str(conflict_decision.get("reason", "cross-agent conflict denied"))
                )
        elif modified_files:
            record["file_ownership_claims"] = {
                "agent_name": str(record.get("agent_name", "")),
                "claimed_files": modified_files,
            }

        elapsed = (datetime.now(timezone.utc) - wall_time_start).total_seconds()
        _record_governed_usage(
            record,
            project_dir=project_dir,
            wall_time_seconds=elapsed,
            output_text=str(dispatch_result.get("output", "")),
        )
        _record_rollback_side_effects(
            record, project_dir=project_dir, modified_files=modified_files
        )

        artifact = {
            "type": "worker-result",
            "agent": record["agent_name"],
            "worker": dispatch_result.get("worker", "unknown"),
            "exit_code": dispatch_result.get("exit_code", 0),
            "output": dispatch_result.get("output", ""),
            "modified_files": modified_files,
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }
        if conflict_decision is not None:
            artifact["conflict_gate"] = conflict_decision
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
            "governed_context": governed_context,
            "modified_files": modified_files,
            "file_ownership": _agent_coordinator.ownership_snapshot(),
            "conflict_gate": record.get("conflict_gate", {}),
            "budget_check": record.get("budget_check", {}),
        }
        evidence_path = _write_job_evidence(
            job_id, evidence_payload, project_dir=project_dir
        )
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
        _logger.debug(
            "Failed to emit cancel evidence for subagent job: %s", exc, exc_info=True
        )

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
