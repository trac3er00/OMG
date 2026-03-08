from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from runtime.release_run_coordinator import resolve_current_run_id
from runtime.test_intent_lock import verify_lock


_MUTATING_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
_EXEMPTIONS = frozenset({"docs", "config", "generated", "test"})
_MUTATION_BASH_PATTERNS = (
    r"\b(git\s+(add|commit|push|rebase|cherry-pick|merge|tag))\b",
    r"\b(rm|mv|cp|tee|touch|mkdir|rmdir|ln)\b",
    r"\b(sed\s+-i|perl\s+-pi)\b",
    r"\b(chmod|chown)\b",
    r">\s*[^\s]",
)


def check_mutation_allowed(
    tool: str,
    file_path: str,
    project_dir: str,
    lock_id: str | None,
    *,
    exemption: str | None = None,
    command: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, str | None]:
    normalized_tool = str(tool or "").strip()
    normalized_file_path = str(file_path or "").strip()
    normalized_lock_id = str(lock_id or "").strip() or None
    normalized_exemption = str(exemption or "").strip().lower() or None
    normalized_command = str(command or "").strip()
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    explicit_exempt = bool(metadata_obj.get("exempt") is True)
    strict_mode = os.environ.get("OMG_TDD_GATE_STRICT", "0").strip() == "1"

    if explicit_exempt:
        return {
            "status": "exempt",
            "reason": "metadata exemption allows mutation without lock",
            "lock_id": normalized_lock_id,
        }

    if normalized_exemption in _EXEMPTIONS:
        return {
            "status": "exempt",
            "reason": f"exemption '{normalized_exemption}' allows mutation without lock",
            "lock_id": normalized_lock_id,
        }

    requires_lock = normalized_tool in _MUTATING_TOOLS
    if normalized_tool == "Bash":
        requires_lock = _is_mutation_capable_bash(normalized_command)

    if not requires_lock:
        return {
            "status": "allowed",
            "reason": "tool is read-only for mutation gate",
            "lock_id": normalized_lock_id,
        }

    resolved_run_id = str(run_id or "").strip() or resolve_current_run_id(project_dir=project_dir)
    verification = verify_lock(project_dir, run_id=resolved_run_id, lock_id=normalized_lock_id)
    if verification.get("status") == "ok":
        return {
            "status": "allowed",
            "reason": "active test intent lock found",
            "lock_id": str(verification.get("lock_id") or normalized_lock_id or "") or None,
        }

    reason = str(verification.get("reason", "no_active_test_intent_lock"))
    if strict_mode:
        _write_block_artifact(project_dir, normalized_tool, normalized_file_path, reason)
        return {
            "status": "blocked",
            "reason": reason,
            "lock_id": normalized_lock_id,
        }

    warnings.warn(
        f"mutation_gate_permissive_allow:{normalized_tool}:{reason}",
        RuntimeWarning,
        stacklevel=2,
    )
    return {
        "status": "allowed",
        "reason": reason,
        "lock_id": normalized_lock_id,
    }


def _is_mutation_capable_bash(command: str) -> bool:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return False
    lowered = normalized_command.lower()
    for pattern in _MUTATION_BASH_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


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
