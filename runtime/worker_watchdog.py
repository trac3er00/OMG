"""Worker lifecycle watchdog — heartbeats, stall detection, termination, and replay evidence.

Monitors workers by run_id, detects stalls, terminates unresponsive workers,
cleans up stale worktrees, and emits replayable evidence for post-mortem analysis.

State paths:
- Heartbeats: .omg/state/worker-heartbeats/<run_id>.json
- Replay evidence: .omg/evidence/subagents/<run_id>-replay.json
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hooks.security_validators import sanitize_run_id


_DEFAULT_STALL_THRESHOLD_SECONDS = 60
_SIGKILL_GRACE_SECONDS = 5


def _project_dir(project_dir: str | None = None) -> Path:
    if project_dir:
        return Path(project_dir)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _active_coordinator_run_id(project_dir: Path) -> str:
    shadow_path = project_dir / ".omg" / "shadow" / "active-run"
    if shadow_path.exists():
        try:
            shadow = shadow_path.read_text(encoding="utf-8").strip()
        except OSError:
            shadow = ""
        if shadow:
            return shadow

    state_dir = project_dir / ".omg" / "state" / "release_run_coordinator"
    if not state_dir.exists():
        return ""
    candidates = sorted(state_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(candidates):
        payload = _read_json(path)
        run_id = str(payload.get("run_id", "")).strip()
        if run_id:
            return run_id
    return ""


class WorkerWatchdog:
    """Monitor workers by run_id with heartbeats, stall detection, and termination."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = _project_dir(project_dir)

    # --- Paths ---

    def _heartbeat_dir(self) -> Path:
        return self.project_dir / ".omg" / "state" / "worker-heartbeats"

    def _heartbeat_path(self, run_id: str) -> Path:
        return self._heartbeat_dir() / f"{sanitize_run_id(run_id)}.json"

    def _replay_evidence_path(self, run_id: str) -> Path:
        return self.project_dir / ".omg" / "evidence" / "subagents" / f"{sanitize_run_id(run_id)}-replay.json"

    def _worktree_dir(self, run_id: str) -> Path:
        return self.project_dir / ".omg" / "worktrees" / sanitize_run_id(run_id)

    def _ownership_metadata(self, run_id: str) -> dict[str, Any]:
        from runtime.merge_writer import get_merge_writer

        active_run_id = _active_coordinator_run_id(self.project_dir)
        merge_writer = get_merge_writer(str(self.project_dir))
        merge_writer_details = merge_writer.check_authorization_details(run_id)
        return {
            "run_id": run_id,
            "active_run_id": active_run_id,
            "merge_writer": merge_writer_details,
        }

    # --- Heartbeats ---

    def record_heartbeat(
        self,
        run_id: str,
        worker_pid: int | None = None,
        *,
        status: str = "alive",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write heartbeat to .omg/state/worker-heartbeats/<run_id>.json.

        Args:
            run_id: The run identifier for this worker.
            worker_pid: Optional PID of the worker subprocess.
            status: Worker status (alive, stalled, terminated, etc.).
            metadata: Optional extra metadata to include.

        Returns:
            The heartbeat record that was persisted.
        """
        path = self._heartbeat_path(run_id)
        existing = _read_json(path)

        heartbeat_count = int(existing.get("heartbeat_count", 0)) + 1

        record: dict[str, Any] = {
            "schema": "WorkerHeartbeat",
            "run_id": run_id,
            "worker_pid": worker_pid or existing.get("worker_pid"),
            "status": status,
            "heartbeat_count": heartbeat_count,
            "last_heartbeat_at": _now_iso(),
            "first_heartbeat_at": existing.get("first_heartbeat_at", _now_iso()),
            "metadata": metadata or existing.get("metadata", {}),
            "ownership": self._ownership_metadata(run_id),
        }

        _write_atomic_json(path, record)
        return record

    def read_heartbeat(self, run_id: str) -> dict[str, Any]:
        """Read heartbeat state for a given run_id.

        Returns:
            Heartbeat record dict, or empty dict if not found.
        """
        return _read_json(self._heartbeat_path(run_id))

    def list_heartbeats(self) -> list[dict[str, Any]]:
        """List all heartbeat records."""
        hb_dir = self._heartbeat_dir()
        if not hb_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        try:
            for path in sorted(hb_dir.glob("*.json")):
                if path.name.endswith(".tmp"):
                    continue
                record = _read_json(path)
                if record:
                    results.append(record)
        except OSError:
            pass
        return results

    def cleanup_terminal_heartbeats(self, max_age_seconds: float) -> list[str]:
        cutoff = datetime.now(timezone.utc).timestamp() - float(max_age_seconds)
        removable_statuses = {"terminated", "completed", "failed"}
        cleaned_run_ids: list[str] = []
        hb_dir = self._heartbeat_dir()
        if not hb_dir.exists():
            return cleaned_run_ids

        for path in sorted(hb_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            record = _read_json(path)
            if not record:
                continue

            status = str(record.get("status", "")).strip().lower()
            if status not in removable_statuses:
                continue

            timestamp = str(record.get("last_heartbeat_at") or record.get("first_heartbeat_at") or "")
            if not timestamp:
                continue

            try:
                parsed = datetime.fromisoformat(timestamp)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue

            if parsed.timestamp() > cutoff:
                continue

            run_id = str(record.get("run_id") or path.stem)
            try:
                path.unlink(missing_ok=True)
                cleaned_run_ids.append(run_id)
            except OSError:
                continue

        return cleaned_run_ids

    # --- Stall Detection ---

    def check_stall(
        self,
        run_id: str,
        stall_threshold_seconds: float = _DEFAULT_STALL_THRESHOLD_SECONDS,
    ) -> bool:
        """Return True if worker is stalled (no heartbeat within threshold).

        A worker is stalled when:
        - It has a heartbeat record with status 'alive'
        - Its last heartbeat timestamp exceeds the stall threshold

        Returns False if no heartbeat exists (worker may not have started).
        """
        record = self.read_heartbeat(run_id)
        if not record:
            return False

        status = str(record.get("status", ""))
        if status in ("terminated", "completed", "failed"):
            return False

        last_heartbeat = record.get("last_heartbeat_at", "")
        if not last_heartbeat:
            return False

        try:
            last_ts = datetime.fromisoformat(last_heartbeat)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - last_ts).total_seconds()
            return elapsed > stall_threshold_seconds
        except (ValueError, TypeError):
            return False

    def get_stalled_workers(
        self,
        stall_threshold_seconds: float = _DEFAULT_STALL_THRESHOLD_SECONDS,
    ) -> list[dict[str, Any]]:
        """Return all heartbeat records for stalled workers."""
        stalled: list[dict[str, Any]] = []
        for record in self.list_heartbeats():
            run_id = str(record.get("run_id", ""))
            if run_id and self.check_stall(run_id, stall_threshold_seconds):
                stalled.append(record)
        return stalled

    # --- Worker Termination ---

    def terminate_worker(
        self,
        run_id: str,
        worker_pid: int,
        *,
        grace_seconds: float = _SIGKILL_GRACE_SECONDS,
    ) -> dict[str, Any]:
        """Terminate a worker subprocess by PID.

        Sends SIGTERM first, waits grace_seconds, then SIGKILL if still alive.

        Args:
            run_id: Run identifier for evidence recording.
            worker_pid: PID to terminate.
            grace_seconds: Seconds to wait after SIGTERM before SIGKILL.

        Returns:
            Termination result dict with status and details.
        """
        result: dict[str, Any] = {
            "run_id": run_id,
            "worker_pid": worker_pid,
            "terminated_at": _now_iso(),
            "sigterm_sent": False,
            "sigkill_sent": False,
            "process_exited": False,
            "error": None,
        }

        try:
            # Check if process exists first
            os.kill(worker_pid, 0)
        except (ProcessLookupError, PermissionError):
            result["process_exited"] = True
            result["error"] = "process_not_found_or_no_permission"
            self.record_heartbeat(run_id, worker_pid, status="terminated")
            return result

        # Send SIGTERM
        try:
            os.kill(worker_pid, signal.SIGTERM)
            result["sigterm_sent"] = True
        except (ProcessLookupError, PermissionError) as exc:
            result["process_exited"] = True
            result["error"] = f"sigterm_failed: {exc}"
            self.record_heartbeat(run_id, worker_pid, status="terminated")
            return result

        # Wait grace period for clean exit
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                result["process_exited"] = True
                self.record_heartbeat(run_id, worker_pid, status="terminated")
                return result
            except PermissionError:
                result["process_exited"] = True
                self.record_heartbeat(run_id, worker_pid, status="terminated")
                return result
            time.sleep(0.1)

        # SIGKILL if still alive
        try:
            os.kill(worker_pid, signal.SIGKILL)
            result["sigkill_sent"] = True
            result["process_exited"] = True
        except (ProcessLookupError, PermissionError):
            result["process_exited"] = True

        self.record_heartbeat(run_id, worker_pid, status="terminated")
        return result

    # --- Worktree Cleanup ---

    def cleanup_stale_worktree(self, run_id: str) -> dict[str, Any]:
        """Remove stale worktree for a dead/terminated worker.

        Uses git worktree remove first, then falls back to shutil.rmtree.

        Returns:
            Cleanup result dict.
        """
        import shutil
        import subprocess

        worktree = self._worktree_dir(run_id)
        result: dict[str, Any] = {
            "run_id": run_id,
            "worktree_path": str(worktree),
            "existed": worktree.is_dir(),
            "cleaned": False,
            "method": None,
            "error": None,
        }

        if not worktree.is_dir():
            return result

        # Try git worktree remove first
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                cwd=str(self.project_dir),
            )
            if not worktree.is_dir():
                result["cleaned"] = True
                result["method"] = "git_worktree_remove"
                return result
        except (subprocess.TimeoutExpired, OSError):
            pass

        # Fallback: rmtree
        try:
            shutil.rmtree(str(worktree), ignore_errors=True)
            result["cleaned"] = not worktree.is_dir()
            result["method"] = "shutil_rmtree"
        except OSError as exc:
            result["error"] = str(exc)

        return result

    # --- Replay Evidence ---

    def emit_replay_evidence(
        self,
        run_id: str,
        reason: str,
        *,
        heartbeat: dict[str, Any] | None = None,
        termination: dict[str, Any] | None = None,
        cleanup: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write replay evidence to .omg/evidence/subagents/<run_id>-replay.json.

        Captures all lifecycle data for post-mortem analysis.

        Returns:
            The evidence payload that was written.
        """
        path = self._replay_evidence_path(run_id)

        payload: dict[str, Any] = {
            "schema": "WorkerReplayEvidence",
            "run_id": run_id,
            "reason": reason,
            "generated_at": _now_iso(),
            "heartbeat_snapshot": heartbeat or self.read_heartbeat(run_id),
            "termination": termination,
            "cleanup": cleanup,
            "extra": {
                **(extra or {}),
                "ownership": self._ownership_metadata(run_id),
            },
        }

        _write_atomic_json(path, payload)
        payload["evidence_path"] = str(path.relative_to(self.project_dir)).replace("\\", "/")
        return payload

    # --- Composite Operations ---

    def cancel_and_cleanup(
        self,
        run_id: str,
        worker_pid: int | None = None,
        *,
        reason: str = "cancelled",
        grace_seconds: float = _SIGKILL_GRACE_SECONDS,
    ) -> dict[str, Any]:
        """Full cancel flow: terminate subprocess, cleanup worktree, emit evidence.

        Args:
            run_id: Run identifier.
            worker_pid: PID of the worker (if known).
            reason: Reason for cancellation.
            grace_seconds: SIGTERM → SIGKILL grace period.

        Returns:
            Composite result with termination, cleanup, and evidence details.
        """
        termination: dict[str, Any] | None = None
        if worker_pid is not None:
            termination = self.terminate_worker(
                run_id, worker_pid, grace_seconds=grace_seconds,
            )

        cleanup = self.cleanup_stale_worktree(run_id)

        evidence = self.emit_replay_evidence(
            run_id,
            reason,
            termination=termination,
            cleanup=cleanup,
        )

        # Mark heartbeat as terminal
        self.record_heartbeat(
            run_id,
            worker_pid,
            status="terminated",
            metadata={"reason": reason},
        )

        return {
            "run_id": run_id,
            "termination": termination,
            "cleanup": cleanup,
            "evidence": evidence,
            "status": "cancelled",
        }

    def escalate_stall(
        self,
        run_id: str,
        *,
        stall_threshold_seconds: float = _DEFAULT_STALL_THRESHOLD_SECONDS,
    ) -> dict[str, Any] | None:
        """Check for stall and escalate if detected.

        Returns escalation result if stalled, None otherwise.
        """
        if not self.check_stall(run_id, stall_threshold_seconds):
            return None

        heartbeat = self.read_heartbeat(run_id)
        worker_pid = heartbeat.get("worker_pid")

        # Mark as stalled
        self.record_heartbeat(run_id, worker_pid, status="stalled")

        # Emit replay evidence for the stall
        evidence = self.emit_replay_evidence(
            run_id,
            f"stall_detected: no heartbeat within {stall_threshold_seconds}s",
            heartbeat=heartbeat,
        )

        return {
            "run_id": run_id,
            "worker_pid": worker_pid,
            "stall_threshold_seconds": stall_threshold_seconds,
            "heartbeat": heartbeat,
            "evidence": evidence,
            "status": "stalled",
        }


def get_worker_watchdog(project_dir: str | None = None) -> WorkerWatchdog:
    """Factory for WorkerWatchdog instances."""
    return WorkerWatchdog(project_dir)
