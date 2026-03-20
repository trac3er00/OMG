from __future__ import annotations

import os
import re
from typing import Callable


_COST_TIER: dict[str, int] = {
    "gemini": 1,
    "codex": 2,
    "ccg": 3,
}

# =============================================================================
# Task-Type Routing (NF5a)
# =============================================================================

TASK_TYPES: dict[str, dict[str, str | None]] = {
    "feature": {"primary": "claude", "fallback": "codex", "strategy": "ccg", "gate": None},
    "bugfix": {"primary": "codex", "fallback": "claude", "strategy": "single", "gate": None},
    "security": {"primary": "codex", "fallback": "claude", "strategy": "single", "gate": "hard"},
    "ui-change": {"primary": "gemini", "fallback": "claude", "strategy": "single", "gate": None},
    "refactor": {"primary": "claude", "fallback": "codex", "strategy": "review", "gate": None},
    "docs": {"primary": "claude", "fallback": None, "strategy": "direct", "gate": None},
    "migration": {"primary": "claude", "fallback": "codex", "strategy": "review", "gate": None},
}

# Keyword patterns for task classification (ordered by priority/specificity)
_TASK_KEYWORDS: dict[str, list[str]] = {
    "security": ["security", "authentication", "authorization", "cve", "cves", "vulnerability", "exploit", "injection", "xss", "csrf"],
    "bugfix": ["fix", "bug", "broken", "error", "crash", "issue", "wrong", "fail"],
    "ui-change": ["ui", "design", "layout", "responsive", "css", "style", "theme", "dark mode", "light mode"],
    "refactor": ["refactor", "rename", "reorganize", "clean up", "cleanup", "restructure", "simplify"],
    "docs": ["docs", "readme", "documentation", "document", "comment", "jsdoc", "docstring"],
    "migration": ["migrate", "upgrade", "move", "transfer", "convert", "port"],
}

# File pattern associations for task classification
_FILE_PATTERNS: dict[str, list[str]] = {
    "backend": [".py", ".go", ".rs", ".java", ".rb", ".php", ".cs"],
    "ui": [".tsx", ".jsx", ".css", ".scss", ".sass", ".less", ".html", ".vue", ".svelte"],
    "migration": ["dockerfile", ".yml", ".yaml", "migration", "migrate", "schema"],
}


def classify_task_type(
    prompt: str,
    files: list[str] | None = None,
    context: str | None = None,
) -> dict[str, str | float | dict | list]:
    """Classify a task based on prompt, files, and context.

    Returns:
        dict with keys:
        - task_type: str (one of TASK_TYPES keys)
        - confidence: float (0.0 to 1.0)
        - routing: dict (the routing config for this task type)
        - signals: list[str] (reasons for classification)
    """
    prompt_lower = prompt.lower()
    signals: list[str] = []
    scores: dict[str, float] = {task_type: 0.0 for task_type in TASK_TYPES}

    # Score based on prompt keywords (word-boundary matching to avoid false positives)
    import re as _re
    for task_type, keywords in _TASK_KEYWORDS.items():
        for keyword in keywords:
            # Multi-word keywords: substring match is fine
            # Single-word: require word boundary to avoid "ui" matching "build"
            if " " in keyword:
                matched = keyword in prompt_lower
            else:
                matched = bool(_re.search(r"\b" + _re.escape(keyword) + r"\b", prompt_lower))
            if matched:
                # Security and bugfix keywords get higher weight
                weight = 2.0 if task_type in ("security", "bugfix") else 1.0
                scores[task_type] += weight
                signals.append(f"keyword:{keyword}->{task_type}")

    # Score based on file patterns
    if files:
        backend_count = 0
        ui_count = 0
        migration_count = 0

        for file_path in files:
            file_lower = file_path.lower()
            file_name = os.path.basename(file_lower)

            # Check backend files
            for ext in _FILE_PATTERNS["backend"]:
                if file_lower.endswith(ext):
                    backend_count += 1
                    break

            # Check UI files
            for ext in _FILE_PATTERNS["ui"]:
                if file_lower.endswith(ext):
                    ui_count += 1
                    break

            # Check migration files
            for pattern in _FILE_PATTERNS["migration"]:
                if pattern in file_name:
                    migration_count += 1
                    break

        # Boost scores based on file patterns
        if ui_count > 0:
            scores["ui-change"] += ui_count * 0.5
            signals.append(f"files:ui({ui_count})")
        if migration_count > 0:
            scores["migration"] += migration_count * 1.0
            signals.append(f"files:migration({migration_count})")
        # Backend files can indicate bugfix or feature
        if backend_count > 0 and scores["bugfix"] > 0:
            scores["bugfix"] += backend_count * 0.3
            signals.append(f"files:backend({backend_count})")

    # Determine winning task type
    max_score = max(scores.values())
    if max_score == 0:
        # No signals matched, default to feature
        task_type = "feature"
        confidence = 0.5
        signals.append("default:feature")
    else:
        # Find task type with highest score
        task_type = max(scores, key=lambda t: scores[t])
        # Confidence based on score relative to max possible
        # Higher scores = higher confidence, capped at 1.0
        confidence = min(1.0, max_score / 3.0)

    routing = get_routing_for_task(task_type)

    return {
        "task_type": task_type,
        "confidence": confidence,
        "routing": routing,
        "signals": signals,
    }


def get_routing_for_task(task_type: str) -> dict[str, str | None]:
    """Look up routing configuration for a task type.

    Args:
        task_type: One of the TASK_TYPES keys

    Returns:
        dict with keys: primary, fallback, strategy, gate
    """
    if task_type not in TASK_TYPES:
        # Unknown task type, return feature routing as default
        return {
            "primary": "claude",
            "fallback": "codex",
            "strategy": "ccg",
            "gate": None,
        }

    config = TASK_TYPES[task_type]
    return {
        "primary": config["primary"],
        "fallback": config["fallback"],
        "strategy": config["strategy"],
        "gate": config.get("gate"),
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


# =============================================================================
# NF5c: Selective agent-as-tool (risk/ambiguity scoring)
# =============================================================================

# Keywords that increase risk score
_RISK_KEYWORDS: dict[str, float] = {
    # Security keywords (+0.3 each)
    "security": 0.3,
    "auth": 0.3,
    "authentication": 0.3,
    "authorization": 0.3,
    "crypto": 0.3,
    "encryption": 0.3,
    "decrypt": 0.3,
    "password": 0.3,
    "secret": 0.3,
    "token": 0.3,
    "jwt": 0.3,
    "oauth": 0.3,
    "cve": 0.3,
    "vulnerability": 0.3,
    "exploit": 0.3,
    "injection": 0.3,
    "xss": 0.3,
    "csrf": 0.3,
    # Migration/infra keywords (+0.2 each)
    "migration": 0.2,
    "migrate": 0.2,
    "infrastructure": 0.2,
    "infra": 0.2,
    "database": 0.2,
    "schema": 0.2,
    "deploy": 0.2,
    "production": 0.2,
    "kubernetes": 0.2,
    "k8s": 0.2,
    "docker": 0.2,
}

# Words that increase ambiguity score
_AMBIGUITY_KEYWORDS: dict[str, float] = {
    # Broad scope words (+0.2 each)
    "everything": 0.2,
    "all": 0.2,
    "entire": 0.2,
    "whole": 0.2,
    "complete": 0.2,
    "full": 0.2,
    "everywhere": 0.2,
    # Vague words (+0.3 each)
    "somehow": 0.3,
    "maybe": 0.3,
    "perhaps": 0.3,
    "something": 0.3,
    "anything": 0.3,
    "stuff": 0.3,
    "things": 0.3,
    "whatever": 0.3,
    "etc": 0.3,
}


def score_task_complexity(
    prompt: str, files: list[str] | None = None
) -> dict[str, float | str]:
    """Score task risk and ambiguity to determine sub-agent usage.

    Args:
        prompt: The task prompt/description.
        files: Optional list of file paths involved.

    Returns:
        dict with keys:
        - risk: float (0.0 to 1.0)
        - ambiguity: float (0.0 to 1.0)
        - recommendation: str ("direct", "isolated", or "ccg")
    """
    prompt_lower = prompt.lower()
    risk_score = 0.0
    ambiguity_score = 0.0

    # Calculate risk from keywords
    for keyword, weight in _RISK_KEYWORDS.items():
        if keyword in prompt_lower:
            risk_score += weight

    # Calculate risk from file count (many files = +0.2)
    if files and len(files) > 5:
        risk_score += 0.2

    # Calculate ambiguity from keywords
    for keyword, weight in _AMBIGUITY_KEYWORDS.items():
        if keyword in prompt_lower:
            ambiguity_score += weight

    # Calculate ambiguity from lack of file specification (+0.2)
    if not files:
        ambiguity_score += 0.2

    # Check for short/vague prompts (+0.3)
    word_count = len(prompt.split())
    if word_count < 5:
        ambiguity_score += 0.3

    # Cap scores at 1.0
    risk_score = min(1.0, risk_score)
    ambiguity_score = min(1.0, ambiguity_score)

    # Determine recommendation
    if risk_score >= 0.6 and ambiguity_score >= 0.6:
        recommendation = "ccg"
    elif risk_score >= 0.3 or ambiguity_score >= 0.3:
        recommendation = "isolated"
    else:
        recommendation = "direct"

    return {
        "risk": risk_score,
        "ambiguity": ambiguity_score,
        "recommendation": recommendation,
    }


def should_use_subagent(prompt: str, files: list[str] | None = None) -> bool:
    """Convenience function to check if a sub-agent should be used.

    Args:
        prompt: The task prompt/description.
        files: Optional list of file paths involved.

    Returns:
        True if recommendation is NOT "direct" (i.e., sub-agent needed).
    """
    result = score_task_complexity(prompt, files)
    return result["recommendation"] != "direct"


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
