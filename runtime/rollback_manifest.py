from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_rollback_manifest(run_id: str, step_id: str) -> dict[str, Any]:
    return {
        "schema": "RollbackManifest",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "step_id": step_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "local_restores": [],
        "compensating_actions": [],
        "side_effects": [],
    }


def classify_side_effect(tool: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = metadata or {}
    if tool in {"write", "edit", "multiedit"}:
        return {
            "category": "local_file",
            "decision": "reversible",
            "reversible": True,
            "reason": "local file shadow restore",
        }

    command = str(payload.get("command", "")).strip().lower()
    if tool == "bash":
        if any(token in command for token in ("rm -rf /", "mkfs", "fdisk", "wipefs", "dd if=")):
            return {
                "category": "irreversible",
                "decision": "blocked",
                "reversible": False,
                "reason": "destructive side effect",
            }

        if "git commit" in command:
            return {
                "category": "git_commit",
                "decision": "reversible",
                "reversible": True,
                "reason": "compensate with git revert",
                "default_compensation": "git revert --no-edit <commit>",
            }

        if any(token in command for token in ("curl ", "wget ", "http ")):
            compensation = payload.get("compensating_action")
            if _has_compensating_action(compensation):
                return {
                    "category": "network_request",
                    "decision": "reversible",
                    "reversible": True,
                    "reason": "declared compensating action",
                }
            return {
                "category": "irreversible",
                "decision": "escalation_required",
                "reversible": False,
                "reason": "network request missing compensation",
            }

    return {
        "category": "irreversible",
        "decision": "escalation_required",
        "reversible": False,
        "reason": "undeclared or unknown side effect",
    }


def record_local_restore(manifest: dict[str, Any], file_path: str, status: str, reason: str = "") -> None:
    local_restores = manifest.setdefault("local_restores", [])
    local_restores.append(
        {
            "file_path": file_path,
            "status": status,
            "reason": reason,
            "recorded_at": _utc_now(),
        }
    )
    manifest["updated_at"] = _utc_now()


def record_compensating_action(
    manifest: dict[str, Any],
    effect_type: str,
    action: str,
    command: str,
    status: str = "declared",
    argv: list[str] | None = None,
) -> None:
    actions = manifest.setdefault("compensating_actions", [])
    entry: dict[str, Any] = {
        "effect_type": effect_type,
        "action": action,
        "command": command,
        "status": status,
        "recorded_at": _utc_now(),
    }
    if argv:
        entry["argv"] = argv
    actions.append(entry)
    manifest["updated_at"] = _utc_now()


def record_side_effect(manifest: dict[str, Any], classification: dict[str, Any]) -> None:
    effects = manifest.setdefault("side_effects", [])
    effects.append(dict(classification))
    manifest["updated_at"] = _utc_now()


def write_rollback_manifest(project_dir: str, manifest: dict[str, Any]) -> str:
    run_id = str(manifest.get("run_id", "unknown")).strip() or "unknown"
    step_id = str(manifest.get("step_id", "unknown")).strip() or "unknown"
    out_dir = Path(project_dir) / ".omg" / "state" / "rollback_manifest"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}-{step_id}.json"
    tmp_path = out_path.with_name(f"{out_path.name}.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(out_path)
    return str(out_path)


def _has_compensating_action(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    argv = payload.get("argv")
    if isinstance(argv, list) and argv:
        return True
    action = str(payload.get("action", "")).strip()
    command = str(payload.get("command", "")).strip()
    return bool(action and command)
