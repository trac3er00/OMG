from __future__ import annotations

from typing import Any

_BEGINNER_FLAGS = (
    "--beginner",
    "--simple",
    "--explain",
    "--guide",
    "--walkthrough",
    "--help",
)

_ENGINEER_FLAGS = (
    "--engineer",
    "--diff",
    "--trace",
    "--debug",
    "--verbose",
    "--technical",
    "--json",
)

_EXEC_FLAGS = (
    "--exec",
    "--kpi",
    "--roi",
    "--summary",
    "--cost",
    "--progress",
    "--dashboard",
)


def _normalize_flags(context: dict[str, Any]) -> list[str]:
    flags = context.get("flags", [])
    if not isinstance(flags, list):
        return []
    return [str(flag).strip().casefold() for flag in flags if str(flag).strip()]


def _includes_any(flags: list[str], markers: tuple[str, ...]) -> bool:
    return any(marker in flag for flag in flags for marker in markers)


def detect_persona(context: dict[str, Any] | None = None) -> str:
    payload = context if isinstance(context, dict) else {}
    flags = _normalize_flags(payload)

    if _includes_any(flags, _EXEC_FLAGS):
        return "exec"
    if _includes_any(flags, _ENGINEER_FLAGS):
        return "engineer"
    if _includes_any(flags, _BEGINNER_FLAGS):
        return "beginner"

    command_count = payload.get("commandCount")
    if isinstance(command_count, int) and command_count >= 12:
        return "engineer"
    if isinstance(command_count, int) and command_count <= 2:
        return "beginner"

    return "beginner"


__all__ = ["detect_persona"]
