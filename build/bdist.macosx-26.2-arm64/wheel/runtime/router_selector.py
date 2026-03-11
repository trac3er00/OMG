from __future__ import annotations

import re
from typing import Callable


_COST_TIER: dict[str, int] = {
    "gemini": 1,
    "codex": 2,
    "ccg": 3,
}


def rank_targets_by_cost(targets: list[str]) -> list[str]:
    return sorted(targets, key=lambda name: _COST_TIER.get(name, 999))


def infer_target(problem: str) -> str:
    p = problem.lower()
    ccg_kw = bool(re.search(r"\bccg\b", p)) or "tri-track" in p or "tri track" in p
    gemini_kw = bool(re.search(r"\bgemini\b", p))
    codex_kw = bool(re.search(r"\bcodex\b", p))

    if ccg_kw or (gemini_kw and codex_kw):
        return "ccg"
    if gemini_kw:
        return "gemini"
    if codex_kw:
        return "codex"

    ui_signals = ["ui", "ux", "layout", "css", "visual", "responsive", "frontend"]
    code_signals = ["auth", "security", "backend", "debug", "performance", "algorithm"]
    ccg_signals = [
        "full-stack",
        "full stack",
        "front-end and back-end",
        "frontend and backend",
        "backend and frontend",
        "cross-functional",
        "review everything",
        "architecture",
        "system design",
        "e2e",
        "end-to-end",
    ]

    ui_hit = any(k in p for k in ui_signals)
    code_hit = any(k in p for k in code_signals)
    ccg_hit = any(k in p for k in ccg_signals)

    if ccg_hit or (ui_hit and code_hit):
        return "ccg"
    if ui_hit:
        return "gemini"
    if code_hit:
        return "codex"
    return "codex"


def select_target(problem: str, context: str) -> dict[str, str]:
    target = infer_target(problem)
    reason = "problem intent matched routing heuristic"
    if context and target == "ccg":
        reason = "cross-functional intent favored dual-track routing"
    elif context:
        reason = "problem intent favored single-track routing"
    return {"target": target, "reason": reason}


def collect_cli_health(
    target: str,
    *,
    check_tool_available: Callable[[str], bool],
    check_tool_auth: Callable[[str], tuple[bool | None, str]],
    install_hints: dict[str, str],
) -> dict[str, dict[str, bool | None | str]]:
    if target == "ccg":
        providers = ("codex", "gemini")
    elif target in ("codex", "gemini"):
        providers = (target,)
    else:
        providers = tuple()

    health: dict[str, dict[str, bool | None | str]] = {}
    for provider in providers:
        available = check_tool_available(provider)
        auth_ok: bool | None = None
        auth_message = "CLI is not installed"
        if available:
            auth_ok, auth_message = check_tool_auth(provider)
        live_connection = bool(available and auth_ok is True)
        health[provider] = {
            "available": available,
            "auth_ok": auth_ok,
            "live_connection": live_connection,
            "status_message": auth_message,
            "install_hint": install_hints.get(provider, ""),
        }
    return health
