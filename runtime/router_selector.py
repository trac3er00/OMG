from __future__ import annotations

import os
import re
from typing import Callable, cast

from runtime.complexity_classifier import classify
from runtime.complexity_scorer import score_complexity
from runtime.subscription_tiers import detect_tier


_COST_TIER: dict[str, int] = {
    "gemini": 1,
    "codex": 2,
    "ccg": 3,
}

_MODEL_FAMILY_BY_TARGET: dict[str, str] = {
    "codex": "gpt-5.4",
    "gemini": "claude",
    "ccg": "claude",
}

_DEFAULT_MODEL_TIERS: dict[str, dict[str, str]] = {
    "claude": {
        "light": "claude-haiku-4-5",
        "balanced": "claude-sonnet-4-5",
        "heavy": "claude-opus-4-5",
    },
    "gpt-5.4": {
        "light": "gpt-5.4-mini",
        "balanced": "gpt-5.4",
        "heavy": "gpt-5.4-thinking",
    },
    "kimi": {
        "light": "kimi-k2-fast",
        "balanced": "kimi-k2",
        "heavy": "kimi-k2-thinking",
    },
}

_COMPLEXITY_TO_TIER: dict[str, str] = {
    "trivial": "light",
    "low": "light",
    "medium": "balanced",
    "high": "heavy",
}

_TIER_ORDER = ("light", "balanced", "heavy")

_AUTO_COMPLEXITY_TO_MODEL_TIER: dict[str, str] = {
    "trivial": "light",
    "simple": "light",
    "medium": "balanced",
    "complex": "heavy",
    "critical": "heavy",
}

_AUTO_COMPLEXITY_TO_MODE: dict[str, str] = {
    "trivial": "fast",
    "simple": "fast",
    "medium": "balanced",
    "complex": "quality",
    "critical": "quality",
}

_AUTO_AGENT_MODEL_FAMILY: dict[str, str] = {
    "visual-engineering": "claude",
    "deep": "gpt-5.4",
    "librarian": "claude",
}

_AUTO_AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "visual-engineering": (
        "ui",
        "ux",
        "layout",
        "css",
        "visual",
        "frontend",
        "responsive",
        "landing page",
        "landing",
        "component",
        "design",
        "theme",
        "style",
    ),
    "deep": (
        "backend",
        "api",
        "server",
        "database",
        "auth",
        "security",
        "algorithm",
        "endpoint",
        "service",
        "migration",
        "debug",
        "fix",
        "refactor",
    ),
    "librarian": (
        "research",
        "investigate",
        "compare",
        "explain",
        "documentation",
        "docs",
        "find",
        "lookup",
        "analyze",
        "why",
    ),
}

_AUTO_CROSS_CUTTING_SIGNALS = (
    "full-stack",
    "full stack",
    "cross-service",
    "cross service",
    "end-to-end",
    "e2e",
    "multi-step",
    "migration",
    "architecture",
    "orchestration",
    "rollout",
)

_AUTO_HIGH_RISK_SIGNALS: dict[str, tuple[str, ...]] = {
    "security": ("security", "xss", "csrf", "injection", "secret", "token"),
    "auth": ("auth", "login", "oauth", "jwt", "permission"),
    "performance": ("performance", "optimize", "latency", "throughput"),
    "breaking": ("breaking", "migration", "deprecate", "rename api"),
    "data_loss": ("delete", "drop", "remove data", "data loss"),
}


def rank_targets_by_cost(targets: list[str]) -> list[str]:
    return sorted(targets, key=lambda name: _COST_TIER.get(name, 999))


def _try_get_feature_flag(flag_name: str, default: bool = False) -> bool:
    try:
        from _common import get_feature_flag  # pyright: ignore[reportMissingImports,reportUnknownVariableType]
    except Exception:
        env_key = f"OMG_{flag_name.upper()}_ENABLED"
        env_value = os.environ.get(env_key, "").strip().lower()
        if env_value in {"1", "true", "yes"}:
            return True
        if env_value in {"0", "false", "no"}:
            return False
        return default
    feature_lookup = cast(Callable[[str, bool], bool], get_feature_flag)
    return bool(feature_lookup(flag_name, default))


def _tier_index(tier: str) -> int:
    try:
        return _TIER_ORDER.index(tier)
    except ValueError:
        return 1


def _downgrade_tier(tier: str) -> str:
    idx = _tier_index(tier)
    return _TIER_ORDER[max(0, idx - 1)]


def _choose_model_tier(
    complexity_category: str, *, budget_low: bool, latency_sensitive: bool
) -> str:
    chosen_tier = _COMPLEXITY_TO_TIER.get(complexity_category, "balanced")
    if budget_low:
        chosen_tier = _downgrade_tier(chosen_tier)
    if latency_sensitive and chosen_tier != "light":
        chosen_tier = _downgrade_tier(chosen_tier)
    return chosen_tier


def _normalize_budget_ratio(
    budget_remaining_ratio: float | None, budget_remaining_usd: float | None
) -> float | None:
    if budget_remaining_ratio is not None:
        return max(0.0, min(1.0, float(budget_remaining_ratio)))
    if budget_remaining_usd is None:
        return None
    tier = detect_tier("claude")
    budget_total = float(tier.get("budget_usd_per_session", 0.0) or 0.0)
    if budget_total <= 0:
        return None
    return max(0.0, min(1.0, float(budget_remaining_usd) / budget_total))


def _resolve_latency_sensitive(context: str, latency_sensitive: bool | None) -> bool:
    if latency_sensitive is not None:
        return bool(latency_sensitive)
    lowered = (context or "").lower()
    return any(
        token in lowered
        for token in ("latency", "real-time", "realtime", "urgent", "fast")
    )


def _resolve_model_tiers(
    model_tiers: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    tiers = dict(model_tiers or _DEFAULT_MODEL_TIERS)
    env_override = os.environ.get("OMG_MODEL_TIER_MAP", "").strip()
    if not env_override:
        return tiers
    try:
        import json

        decoded_obj_raw: object = json.loads(env_override)  # pyright: ignore[reportAny]
    except Exception:
        return tiers
    if not isinstance(decoded_obj_raw, dict):
        return tiers
    decoded = cast(dict[str, object], decoded_obj_raw)
    merged: dict[str, dict[str, str]] = {}
    for family, defaults in tiers.items():
        candidate = decoded.get(family)
        if not isinstance(candidate, dict):
            merged[family] = dict(defaults)
            continue
        candidate_map = cast(dict[str, object], candidate)
        merged[family] = {
            "light": str(candidate_map.get("light", defaults.get("light", ""))),
            "balanced": str(
                candidate_map.get("balanced", defaults.get("balanced", ""))
            ),
            "heavy": str(candidate_map.get("heavy", defaults.get("heavy", ""))),
        }
    return merged


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _infer_task_type(goal: str) -> str:
    if any(keyword in goal for keyword in ("refactor", "restructure", "cleanup")):
        return "refactor"
    if any(keyword in goal for keyword in ("optimize", "performance", "latency")):
        return "perf"
    if any(keyword in goal for keyword in ("breaking", "migration", "deprecate")):
        return "breaking"
    if any(keyword in goal for keyword in ("fix", "bug", "debug", "repair")):
        return "fix"
    if any(keyword in goal for keyword in ("test", "spec", "coverage")):
        return "test"
    if any(keyword in goal for keyword in ("docs", "documentation", "readme")):
        return "docs"
    return "feat"


def _infer_test_requirements(goal: str) -> str:
    if any(keyword in goal for keyword in ("end-to-end", "e2e", "user journey")):
        return "e2e"
    if any(keyword in goal for keyword in ("integration", "contract", "cross-service")):
        return "integration"
    return "unit"


def _build_auto_complexity_task(goal: str) -> dict[str, object]:
    lowered = goal.lower()
    tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if token]
    token_count = len(tokens)

    files = 1
    lines_changed = 5
    if token_count >= 8:
        files = 2
        lines_changed = 20
    if token_count >= 18:
        files = 4
        lines_changed = 60
    if token_count >= 35:
        files = 8
        lines_changed = 180

    cross_cutting = any(signal in lowered for signal in _AUTO_CROSS_CUTTING_SIGNALS)
    modules = 1
    if any(keyword in lowered for keyword in ("api", "backend", "frontend", "database", "service")):
        modules = 2
    if cross_cutting:
        files = max(files, 8)
        lines_changed = max(lines_changed, 180)
        modules = 4

    risk_indicators = [
        risk
        for risk, keywords in _AUTO_HIGH_RISK_SIGNALS.items()
        if any(keyword in lowered for keyword in keywords)
    ]

    if risk_indicators:
        lines_changed = max(lines_changed, 80)
        files = max(files, 3)

    return {
        "files": files,
        "lines_changed": lines_changed,
        "cross_cutting": cross_cutting,
        "modules": modules,
        "risk_indicators": risk_indicators,
        "type": _infer_task_type(lowered),
        "test_requirements": _infer_test_requirements(lowered),
    }


def _select_auto_agent(goal: str) -> tuple[str, str]:
    lowered = goal.lower()
    scored_hits = {
        agent: _keyword_hits(lowered, keywords)
        for agent, keywords in _AUTO_AGENT_KEYWORDS.items()
    }
    best_agent = max(scored_hits, key=lambda agent: len(scored_hits[agent]))
    matched_keywords = scored_hits[best_agent]
    if matched_keywords:
        sample = ", ".join(matched_keywords[:3])
        return best_agent, f"matched {best_agent} keywords: {sample}"

    inferred_target = infer_target(goal)
    if inferred_target == "gemini":
        return "visual-engineering", "fallback to visual routing via infer_target()"
    if inferred_target == "codex":
        return "deep", "fallback to backend/deep routing via infer_target()"
    return "deep", "fallback to deep routing for general implementation work"


def auto_select(goal: str, overrides: dict[str, str] | None = None) -> dict[str, object]:
    complexity = classify(_build_auto_complexity_task(goal))
    complexity_tier = complexity.tier
    agent, agent_reason = _select_auto_agent(goal)
    model_tier = _AUTO_COMPLEXITY_TO_MODEL_TIER.get(complexity_tier, "balanced")
    mode = _AUTO_COMPLEXITY_TO_MODE.get(complexity_tier, "balanced")
    model_family = _AUTO_AGENT_MODEL_FAMILY.get(agent, "claude")
    tiers = _resolve_model_tiers(None)
    family_tiers = tiers.get(model_family, _DEFAULT_MODEL_TIERS["claude"])
    model = family_tiers.get(model_tier) or family_tiers.get("balanced", "")

    selection: dict[str, object] = {
        "agent": agent,
        "model": model,
        "mode": mode,
        "reasoning": (
            f"{agent_reason}; complexity={complexity_tier} "
            f"({complexity.reasoning}); selected family={model_family}, tier={model_tier}, mode={mode}"
        ),
        "auto_selected": True,
    }

    if overrides:
        applied: list[str] = []
        for key in ("agent", "model", "mode"):
            override_value = overrides.get(key)
            if override_value:
                selection[key] = override_value
                applied.append(f"{key}={override_value}")
        if applied:
            selection["reasoning"] = (
                f"{selection['reasoning']}; manual override applied ({', '.join(applied)})"
            )

    return selection


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


def select_target(
    problem: str,
    context: str,
    *,
    budget_remaining_ratio: float | None = None,
    budget_remaining_usd: float | None = None,
    latency_sensitive: bool | None = None,
    model_tiers: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    target = infer_target(problem)
    reason = "problem intent matched routing heuristic"
    if context and target == "ccg":
        reason = "cross-functional intent favored dual-track routing"
    elif context:
        reason = "problem intent favored single-track routing"

    if not _try_get_feature_flag("multi_model_routing", default=False):
        return {"target": target, "reason": reason}

    complexity = score_complexity(problem)
    complexity_category = str(complexity.get("category", "medium"))
    remaining_ratio = _normalize_budget_ratio(
        budget_remaining_ratio, budget_remaining_usd
    )
    is_budget_low = remaining_ratio is not None and remaining_ratio < 0.2
    is_latency_sensitive = _resolve_latency_sensitive(context, latency_sensitive)
    selected_tier = _choose_model_tier(
        complexity_category,
        budget_low=is_budget_low,
        latency_sensitive=is_latency_sensitive,
    )
    tiers = _resolve_model_tiers(model_tiers)
    family_models: dict[str, str] = {}
    for family, family_tiers in tiers.items():
        family_models[family] = family_tiers.get(selected_tier) or family_tiers.get(
            "balanced", ""
        )

    selected_family = _MODEL_FAMILY_BY_TARGET.get(target, "claude")
    selected_model = family_models.get(selected_family, "")
    detail_parts = [
        f"complexity={complexity_category}",
        f"tier={selected_tier}",
        f"family={selected_family}",
    ]
    if is_budget_low:
        detail_parts.append("budget<20%")
    if is_latency_sensitive:
        detail_parts.append("latency_sensitive")
    enhanced_reason = f"{reason}; multi-model routing ({', '.join(detail_parts)})"

    return {
        "target": target,
        "reason": enhanced_reason,
        "model_family": selected_family,
        "model_tier": selected_tier,
        "model": selected_model,
        "complexity": complexity,
        "budget_remaining_ratio": remaining_ratio,
        "latency_sensitive": is_latency_sensitive,
        "model_recommendations": family_models,
    }


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
