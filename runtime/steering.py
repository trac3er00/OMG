"""Minimal failure steering entry points for CLI-driven rerouting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STEERING_LOG_REL_PATH = Path(".omg") / "state" / "steering_log.jsonl"


def handle_failure(failure_type: str, context: dict[str, Any]) -> dict[str, str]:
    """Map a failure to a steering action and persist the event."""
    normalized = failure_type.strip().lower()
    decision = _build_decision(normalized, context)
    _log_steering_event(normalized, context, decision)
    return decision


def _build_decision(
    failure_type: str,
    context: dict[str, Any],
) -> dict[str, str]:
    command = str(context.get("command", "workflow")).strip() or "workflow"

    if failure_type == "loop":
        return {
            "action": "reroute",
            "message": f"Detected a repeated {command} loop; reroute to a different path.",
        }
    if failure_type == "cost_spike":
        return {
            "action": "pause",
            "message": f"{command} cost is above expectation; pause before spending more budget.",
        }
    if failure_type == "stuck":
        return {
            "action": "escalate",
            "message": f"{command} is no longer making progress; escalate for a fresh approach.",
        }
    return {
        "action": "inspect",
        "message": f"Unknown failure type '{failure_type}'; inspect context before proceeding.",
    }


def _log_steering_event(
    failure_type: str,
    context: dict[str, Any],
    decision: dict[str, str],
) -> None:
    project_dir = _resolve_project_dir(context)
    log_path = project_dir / STEERING_LOG_REL_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_type": failure_type,
        "decision": decision,
        "context": context,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _resolve_project_dir(context: dict[str, Any]) -> Path:
    project_dir = context.get("project_dir")
    if isinstance(project_dir, str) and project_dir.strip():
        return Path(project_dir).resolve()
    return Path.cwd().resolve()


__all__ = ["handle_failure", "STEERING_LOG_REL_PATH"]
