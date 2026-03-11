from __future__ import annotations

from collections.abc import Mapping
from typing import cast


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [str(item) for item in items]


def build_loop_policy(
    host: str,
    max_iterations: int,
    timeout_minutes: int,
    read_only_default: bool = True,
) -> dict[str, object]:
    return {
        "host": host,
        "max_iterations": max_iterations,
        "timeout_minutes": timeout_minutes,
        "read_only_default": read_only_default,
    }


def should_continue_loop(state: Mapping[str, object]) -> dict[str, object]:
    iteration = _as_int(state.get("iteration", 0), 0)
    max_iterations = _as_int(state.get("max_iterations", 0), 0)
    status = str(state.get("status", ""))

    if iteration >= max_iterations:
        return {"continue": False, "reason": "max_iterations_reached"}
    if status == "ok":
        return {"continue": False, "reason": "status_ok"}
    return {"continue": True, "reason": "within_budget"}


def summarize_next_step(state: Mapping[str, object]) -> dict[str, object]:
    status = str(state.get("status", ""))
    blockers = _as_string_list(state.get("blockers"))
    evidence_links = _as_string_list(state.get("evidence_links"))

    if blockers:
        next_action = f"resolve blockers: {', '.join(blockers)}"
    elif status in {"error", "blocked"}:
        next_action = "verify evidence links and remediate verification errors"
    elif evidence_links:
        next_action = "verify evidence links"
    else:
        next_action = "collect verification evidence links"

    return {
        "next_action": next_action,
        "evidence_links": evidence_links,
        "blockers": blockers,
    }
