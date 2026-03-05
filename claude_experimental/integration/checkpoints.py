"""Human-in-the-loop checkpoint system for pausing execution at critical decision points.

Provides a polling-based checkpoint mechanism that allows agents to pause at
critical decision points (verification, decision, clarification) and wait for
human input before proceeding. Checkpoints are persisted as JSON files in
`.omg/state/checkpoints/` with atomic writes for crash safety.

Feature-gated behind OMG_ADVANCED_INTEGRATION_ENABLED=1.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECKPOINT_DIR = os.path.join(".omg", "state", "checkpoints")
_SCHEMA_VERSION = 1


class CheckpointType(str, Enum):
    """Supported checkpoint types."""

    VERIFICATION = "VERIFICATION"
    DECISION = "DECISION"
    CLARIFICATION = "CLARIFICATION"


class CheckpointStatus(str, Enum):
    """Checkpoint lifecycle states."""

    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_integration() -> None:
    """Gate all public operations behind the ADVANCED_INTEGRATION flag."""
    from claude_experimental.integration import _require_enabled
    _require_enabled()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(iso_str: str) -> datetime:
    # Handle both +00:00 and Z suffixes
    s = iso_str.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _atomic_json_write(path: str, data: dict[str, Any]) -> None:
    """Write JSON atomically: temp file → os.replace().

    Creates parent directories if needed.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent, suffix=".tmp", prefix=".ckpt_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_checkpoint_file(path: str) -> dict[str, Any] | None:
    """Read and parse a checkpoint JSON file. Returns None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Manages human-in-the-loop checkpoints for pausing execution.

    Checkpoints are persisted as individual JSON files under
    ``{base_dir}/.omg/state/checkpoints/{checkpoint_id}.json``.

    Usage::

        mgr = CheckpointManager()
        cid = mgr.create_checkpoint(
            checkpoint_type="DECISION",
            description="Choose deployment target",
            options=["staging", "production"],
        )
        # ... poll or wait ...
        mgr.resume_checkpoint(cid, decision="staging")
    """

    def __init__(self, base_dir: str = ".") -> None:
        self._checkpoint_dir = os.path.join(base_dir, _CHECKPOINT_DIR)

    # -- public API ---------------------------------------------------------

    def create_checkpoint(
        self,
        checkpoint_type: str,
        description: str,
        options: list[str] | None = None,
        timeout_seconds: int = 3600,
    ) -> str:
        """Create a new pending checkpoint.

        Args:
            checkpoint_type: One of VERIFICATION, DECISION, CLARIFICATION.
            description: Human-readable description of what needs attention.
            options: Optional list of valid choices (useful for DECISION type).
            timeout_seconds: Seconds until the checkpoint auto-expires (default 3600).

        Returns:
            checkpoint_id: UUID string for the new checkpoint.

        Raises:
            RuntimeError: If the feature flag is disabled.
            ValueError: If checkpoint_type is invalid.
        """
        _require_integration()

        # Validate type
        try:
            ct = CheckpointType(checkpoint_type)
        except ValueError:
            valid = ", ".join(t.value for t in CheckpointType)
            raise ValueError(
                f"Invalid checkpoint type '{checkpoint_type}'. "
                f"Must be one of: {valid}"
            ) from None

        checkpoint_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(
            now.timestamp() + timeout_seconds, tz=timezone.utc
        )

        checkpoint_data: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "type": ct.value,
            "description": description,
            "options": options if options is not None else [],
            "status": CheckpointStatus.PENDING.value,
            "decision": None,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "schema_version": _SCHEMA_VERSION,
        }

        path = os.path.join(self._checkpoint_dir, f"{checkpoint_id}.json")
        _atomic_json_write(path, checkpoint_data)
        return checkpoint_id

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Retrieve the current state of a checkpoint.

        Args:
            checkpoint_id: UUID of the checkpoint.

        Returns:
            Checkpoint dict with all fields.

        Raises:
            RuntimeError: If the feature flag is disabled.
            KeyError: If checkpoint not found.
        """
        _require_integration()

        path = os.path.join(self._checkpoint_dir, f"{checkpoint_id}.json")
        data = _read_checkpoint_file(path)
        if data is None:
            raise KeyError(f"Checkpoint not found: {checkpoint_id}")

        # Auto-expire if past deadline
        if data.get("status") == CheckpointStatus.PENDING.value:
            expires_at = _parse_iso(str(data["expires_at"]))
            if datetime.now(timezone.utc) > expires_at:
                data["status"] = CheckpointStatus.EXPIRED.value
                _atomic_json_write(path, data)

        return data

    def resume_checkpoint(self, checkpoint_id: str, decision: str) -> bool:
        """Resolve a pending checkpoint with a human decision.

        Args:
            checkpoint_id: UUID of the checkpoint to resume.
            decision: The decision string from the human.

        Returns:
            True if the checkpoint was successfully resolved.
            False if the checkpoint was not in pending state.

        Raises:
            RuntimeError: If the feature flag is disabled.
            KeyError: If checkpoint not found.
        """
        _require_integration()

        path = os.path.join(self._checkpoint_dir, f"{checkpoint_id}.json")
        data = _read_checkpoint_file(path)
        if data is None:
            raise KeyError(f"Checkpoint not found: {checkpoint_id}")

        # Can only resume pending checkpoints
        if data.get("status") != CheckpointStatus.PENDING.value:
            return False

        # Check expiry
        expires_at = _parse_iso(str(data["expires_at"]))
        if datetime.now(timezone.utc) > expires_at:
            data["status"] = CheckpointStatus.EXPIRED.value
            _atomic_json_write(path, data)
            return False

        data["status"] = CheckpointStatus.RESOLVED.value
        data["decision"] = decision
        _atomic_json_write(path, data)
        return True

    def list_pending(self) -> list[dict[str, Any]]:
        """List all checkpoints currently in pending state.

        Returns:
            List of checkpoint dicts with status=pending.
            Expired checkpoints are auto-transitioned and excluded.

        Raises:
            RuntimeError: If the feature flag is disabled.
        """
        _require_integration()

        pending: list[dict[str, Any]] = []

        if not os.path.isdir(self._checkpoint_dir):
            return pending

        now = datetime.now(timezone.utc)

        for filename in os.listdir(self._checkpoint_dir):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self._checkpoint_dir, filename)
            data = _read_checkpoint_file(path)
            if data is None:
                continue

            if data.get("status") != CheckpointStatus.PENDING.value:
                continue

            # Auto-expire
            expires_at = _parse_iso(str(data["expires_at"]))
            if now > expires_at:
                data["status"] = CheckpointStatus.EXPIRED.value
                _atomic_json_write(path, data)
                continue

            pending.append(data)

        return pending

    def cleanup_expired(self) -> int:
        """Remove checkpoint files that have expired.

        Deletes files where expires_at < now, regardless of current status.

        Returns:
            Number of expired checkpoint files removed.

        Raises:
            RuntimeError: If the feature flag is disabled.
        """
        _require_integration()

        removed = 0

        if not os.path.isdir(self._checkpoint_dir):
            return removed

        now = datetime.now(timezone.utc)

        for filename in os.listdir(self._checkpoint_dir):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self._checkpoint_dir, filename)
            data = _read_checkpoint_file(path)
            if data is None:
                continue

            expires_at = _parse_iso(str(data["expires_at"]))
            if now > expires_at:
                try:
                    os.unlink(path)
                    removed += 1
                except OSError:
                    pass

        return removed
