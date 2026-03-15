"""Merge-writer lock — single authorized writer for main-tree mutations.

Enforces one-writer/many-readers semantics:
- Read-only workers run concurrently without obtaining the merge lock.
- Mutation-capable workers MUST hold the merge-writer lock AND run
  inside a worktree before applying changes back to the main tree.

Write leases extend the merge-writer lock with run-scoped, time-bounded
authorization.  A write lease is NOT a second lock — it layers on top of
the existing single-writer lock, adding temporal and evidence constraints.

Lock file:     .omg/state/merge-writer.lock   (JSON)
Provenance:    .omg/evidence/merge-writer-<run_id>.json
"""
from __future__ import annotations

import json
import os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import cast


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MergeWriterAuthorizationError(RuntimeError):
    """Raised when an unauthorized worker attempts a main-tree mutation."""

    def __init__(self, run_id: str, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(
            f"merge-writer authorization denied for run_id={run_id}: {reason}"
        )


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MergeWriterToken:
    """Proof-of-ownership token returned by MergeWriter.acquire()."""

    run_id: str
    acquired_at: str
    lock_path: str
    provenance_path: str


# ---------------------------------------------------------------------------
# MergeWriter
# ---------------------------------------------------------------------------

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


class MergeWriter:
    """Single merge-writer lock manager with provenance.

    Usage::

        mw = MergeWriter("/path/to/project")
        token = mw.acquire("run-abc", reason="release merge")
        # ... perform mutation ...
        mw.release(token)
    """

    def __init__(self, project_dir: str | None = None) -> None:
        if project_dir:
            self.project_dir = Path(project_dir).resolve()
        else:
            self.project_dir = Path(
                os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
            ).resolve()

    # --- Path helpers -------------------------------------------------------

    def _lock_path(self) -> Path:
        return self.project_dir / ".omg" / "state" / "merge-writer.lock"

    def _provenance_path(self, run_id: str) -> Path:
        return self.project_dir / ".omg" / "evidence" / f"merge-writer-{run_id}.json"

    def _active_coordinator_run_id(self) -> str:
        shadow_path = self.project_dir / ".omg" / "shadow" / "active-run"
        if shadow_path.exists():
            try:
                shadow = shadow_path.read_text(encoding="utf-8").strip()
            except OSError:
                shadow = ""
            if shadow:
                return shadow

        state_dir = self.project_dir / ".omg" / "state" / "release_run_coordinator"
        if not state_dir.exists():
            return ""
        candidates = sorted(state_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for path in reversed(candidates):
            payload = _read_json(path)
            if not payload:
                continue
            payload_dict = cast(dict[str, object], payload)
            run_id = str(payload_dict.get("run_id", "")).strip()
            if run_id:
                return run_id
        return ""

    # --- Public API ---------------------------------------------------------

    def acquire(self, run_id: str, reason: str = "") -> MergeWriterToken:
        """Acquire the merge-writer lock.

        Args:
            run_id:  Unique identifier for the writer (typically a release run).
            reason:  Human-readable reason for acquiring the lock.

        Returns:
            A ``MergeWriterToken`` proving ownership.

        Raises:
            MergeWriterAuthorizationError: If the lock is already held by
                a different run_id.
        """
        lock_path = self._lock_path()
        existing = _read_json(lock_path)

        if existing:
            existing_run_id = existing.get("run_id", "")
            if existing_run_id and existing_run_id != run_id:
                raise MergeWriterAuthorizationError(
                    run_id,
                    f"lock already held by run_id={existing_run_id}",
                )

        now = _now_iso()
        lock_payload: dict[str, Any] = {
            "run_id": run_id,
            "acquired_at": now,
            "reason": reason,
            "pid": os.getpid(),
        }
        _write_atomic_json(lock_path, lock_payload)

        provenance_path = self._provenance_path(run_id)
        rel_lock = str(lock_path.relative_to(self.project_dir)).replace("\\", "/")
        rel_prov = str(provenance_path.relative_to(self.project_dir)).replace("\\", "/")

        return MergeWriterToken(
            run_id=run_id,
            acquired_at=now,
            lock_path=rel_lock,
            provenance_path=rel_prov,
        )

    def release(self, token: MergeWriterToken) -> dict[str, Any]:
        """Release the merge-writer lock and write provenance.

        Args:
            token: The token returned by :meth:`acquire`.

        Returns:
            Provenance evidence dict written to disk.

        Raises:
            MergeWriterAuthorizationError: If the caller does not own the lock.
        """
        lock_path = self._lock_path()
        existing = _read_json(lock_path)

        if existing.get("run_id") != token.run_id:
            raise MergeWriterAuthorizationError(
                token.run_id,
                "cannot release: lock is not held by this run_id",
            )

        provenance: dict[str, Any] = {
            "schema": "MergeWriterProvenance",
            "run_id": token.run_id,
            "acquired_at": token.acquired_at,
            "released_at": _now_iso(),
            "lock_path": token.lock_path,
            "provenance_path": token.provenance_path,
            "pid": existing.get("pid"),
            "reason": existing.get("reason", ""),
        }

        provenance_path = self._provenance_path(token.run_id)
        _write_atomic_json(provenance_path, provenance)

        # Remove lock file
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

        return provenance

    def is_locked(self) -> bool:
        """Return True if the merge-writer lock is currently held."""
        lock_path = self._lock_path()
        if not lock_path.exists():
            return False
        existing = _read_json(lock_path)
        return bool(existing.get("run_id"))

    def get_current_owner(self) -> str | None:
        """Return run_id of the current lock holder, or None."""
        existing = _read_json(self._lock_path())
        run_id = existing.get("run_id", "")
        return run_id if run_id else None

    def check_authorization_details(self, run_id: str) -> dict[str, Any]:
        owner_run_id = self.get_current_owner() or ""
        active_run_id = self._active_coordinator_run_id()
        owner_matches = bool(owner_run_id) and owner_run_id == run_id
        active_matches = (not active_run_id) or active_run_id == run_id
        authorized = owner_matches and active_matches

        reason = "authorized"
        if not owner_run_id:
            reason = "merge_writer_lock_missing"
        elif owner_run_id != run_id:
            reason = f"merge_writer_owner_mismatch:{owner_run_id}"
        elif active_run_id and active_run_id != run_id:
            reason = f"active_run_mismatch:{active_run_id}"

        return {
            "run_id": run_id,
            "owner_run_id": owner_run_id,
            "active_run_id": active_run_id,
            "owner_matches": owner_matches,
            "active_matches": active_matches,
            "authorized": authorized,
            "reason": reason,
        }

    def check_authorization(self, run_id: str) -> bool:
        """Return True if *run_id* is the current authorized writer."""
        return bool(self.check_authorization_details(run_id).get("authorized"))

    # --- Governance helpers -------------------------------------------------

    def require_authorization(
        self,
        run_id: str,
        *,
        mutation_type: str = "merge",
        isolation: str = "none",
    ) -> None:
        """Gate a mutation attempt: block if unauthorized.

        Mutation-capable workers MUST:
        1. Run inside a worktree (isolation == "worktree").
        2. Hold the merge-writer lock for their run_id.

        Read-only workers (isolation != "worktree") are allowed through
        without the lock.

        Raises:
            MergeWriterAuthorizationError: On unauthorized mutation.
        """
        normalized_isolation = str(isolation).strip().lower()

        # Read-only workers never need the merge-writer lock
        if normalized_isolation != "worktree":
            return

        if not self.is_locked():
            raise MergeWriterAuthorizationError(
                run_id,
                f"mutation_type={mutation_type} requires merge-writer lock "
                f"but no lock is held",
            )

        details = self.check_authorization_details(run_id)
        if not details.get("authorized"):
            owner = str(details.get("owner_run_id") or "unknown")
            active = str(details.get("active_run_id") or "")
            if active and active != run_id:
                raise MergeWriterAuthorizationError(
                    run_id,
                    f"mutation_type={mutation_type} denied: active coordinator run_id="
                    f"{active}, not {run_id}",
                )
            raise MergeWriterAuthorizationError(
                run_id,
                f"mutation_type={mutation_type} denied: lock held by "
                f"run_id={owner}, not {run_id}",
            )


# ---------------------------------------------------------------------------
# Write Lease — run-scoped, time-bounded authorization over merge writer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteLease:
    """Run-scoped, time-bounded authorization layered over the merge writer.

    A write lease is NOT a second lock.  It constrains an already-held
    merge-writer lock with temporal bounds and evidence linkage.
    """

    run_id: str
    created_at: float  # monotonic seconds (time.monotonic())
    duration_s: float
    evidence_path: str
    is_active: bool = True


def create_write_lease(
    run_id: str,
    duration_s: float,
    evidence_path: str,
) -> WriteLease:
    """Create a new write lease bound to *run_id*.

    Args:
        run_id:         The release-run identifier this lease is scoped to.
        duration_s:     Maximum lifetime in seconds.
        evidence_path:  Path to the evidence artifact backing this lease.

    Returns:
        A ``WriteLease`` instance.
    """
    return WriteLease(
        run_id=run_id,
        created_at=_time.monotonic(),
        duration_s=float(duration_s),
        evidence_path=str(evidence_path),
        is_active=True,
    )


def is_lease_valid(
    lease: WriteLease,
    current_run_id: str,
    current_time: float | None = None,
) -> tuple[bool, str]:
    """Check whether *lease* is still valid for *current_run_id*.

    Args:
        lease:           The lease to validate.
        current_run_id:  The run_id of the currently active release run.
        current_time:    Monotonic timestamp (defaults to ``time.monotonic()``).

    Returns:
        ``(True, "valid")`` when the lease authorizes the run, or
        ``(False, reason)`` with a deterministic blocker reason.
    """
    if not lease.is_active:
        return False, "write_lease_inactive"

    if lease.run_id != current_run_id:
        return (
            False,
            f"write_lease_run_id_mismatch:lease={lease.run_id},current={current_run_id}",
        )

    now = current_time if current_time is not None else _time.monotonic()
    elapsed = now - lease.created_at
    if elapsed > lease.duration_s:
        return (
            False,
            f"write_lease_expired:elapsed={elapsed:.1f}s,limit={lease.duration_s:.1f}s",
        )

    if not lease.evidence_path:
        return False, "write_lease_missing_evidence_path"

    return True, "valid"


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def get_merge_writer(project_dir: str | None = None) -> MergeWriter:
    """Factory for MergeWriter instances."""
    return MergeWriter(project_dir)
