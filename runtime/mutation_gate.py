from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


_MUTATING_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
_EXEMPTIONS = frozenset({"docs", "config", "generated", "test"})


def check_mutation_allowed(
    tool: str,
    file_path: str,
    project_dir: str,
    lock_id: str | None,
    *,
    exemption: str | None = None,
) -> dict[str, str | None]:
    normalized_tool = str(tool or "").strip()
    normalized_file_path = str(file_path or "").strip()
    normalized_lock_id = str(lock_id or "").strip() or None
    normalized_exemption = str(exemption or "").strip().lower() or None

    if normalized_exemption in _EXEMPTIONS:
        return {
            "status": "exempt",
            "reason": f"exemption '{normalized_exemption}' allows mutation without lock",
            "lock_id": normalized_lock_id,
        }

    if normalized_tool not in _MUTATING_TOOLS:
        return {
            "status": "allowed",
            "reason": "tool is read-only for mutation gate",
            "lock_id": normalized_lock_id,
        }

    if normalized_lock_id and _lock_exists(project_dir, normalized_lock_id):
        return {
            "status": "allowed",
            "reason": "active test intent lock found",
            "lock_id": normalized_lock_id,
        }

    reason = (
        "mutation denied: active test intent lock is required for mutation tools"
        if not normalized_lock_id
        else f"mutation denied: lock_id '{normalized_lock_id}' not found"
    )
    _write_block_artifact(project_dir, normalized_tool, normalized_file_path, reason)
    return {
        "status": "blocked",
        "reason": reason,
        "lock_id": normalized_lock_id,
    }


def _lock_exists(project_dir: str, lock_id: str) -> bool:
    lock_path = Path(project_dir) / ".omg" / "state" / "test-intent-lock" / f"{lock_id}.json"
    return lock_path.is_file()


def _write_block_artifact(project_dir: str, tool: str, file_path: str, reason: str) -> None:
    state_dir = Path(project_dir) / ".omg" / "state" / "mutation_gate"
    state_dir.mkdir(parents=True, exist_ok=True)

    path_hash = sha256(file_path.encode("utf-8")).hexdigest()[:8]
    artifact_path = state_dir / f"{path_hash}.json"
    payload = {
        "status": "blocked",
        "tool": tool,
        "file_path": file_path,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    temp_path = artifact_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temp_path, artifact_path)
