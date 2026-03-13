"""Merge-writer lock — single authorized writer for main-tree mutations.

Enforces one-writer/many-readers semantics:
- Read-only workers run concurrently without obtaining the merge lock.
- Mutation-capable workers MUST hold the merge-writer lock AND run
  inside a worktree before applying changes back to the main tree.

Lock file:     .omg/state/merge-writer.lock   (JSON)
Provenance:    .omg/evidence/merge-writer-<run_id>.json
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def check_authorization(self, run_id: str) -> bool:
        """Return True if *run_id* is the current authorized writer."""
        return self.get_current_owner() == run_id

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

        if not self.check_authorization(run_id):
            owner = self.get_current_owner() or "unknown"
            raise MergeWriterAuthorizationError(
                run_id,
                f"mutation_type={mutation_type} denied: lock held by "
                f"run_id={owner}, not {run_id}",
            )


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def get_merge_writer(project_dir: str | None = None) -> MergeWriter:
    """Factory for MergeWriter instances."""
    return MergeWriter(project_dir)
