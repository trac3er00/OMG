from __future__ import annotations

import importlib
import os
import shutil
from typing import Any

from runtime.canonical_surface import is_canonical_parity_host
from runtime.cli_provider import get_provider


_PROVIDERS = ("claude", "codex", "gemini", "kimi")

_COST_TIERS: dict[str, str] = {
    "kimi": "low",
    "gemini": "low",
    "codex": "medium",
    "claude": "high",
}

_COST_SCORE: dict[str, int] = {
    "low": 3,
    "medium": 2,
    "high": 1,
}

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ui_frontend": (
        "ui",
        "ux",
        "frontend",
        "responsive",
        "layout",
        "css",
        "design",
        "component",
        "visual",
    ),
    "code_refactor": (
        "code",
        "refactor",
        "bug",
        "fix",
        "debug",
        "backend",
        "function",
        "api",
        "test",
    ),
    "complex_architecture": (
        "architecture",
        "complex",
        "system",
        "tradeoff",
        "strategy",
        "multi-step",
        "cross-functional",
        "distributed",
    ),
    "fast_simple": (
        "quick",
        "simple",
        "minor",
        "small",
        "fast",
        "typo",
        "rename",
        "trivial",
    ),
}

_DOMAIN_PROVIDER_PREFS: dict[str, tuple[str, ...]] = {
    "ui_frontend": ("gemini", "claude", "codex", "kimi"),
    "code_refactor": ("codex", "claude", "gemini", "kimi"),
    "complex_architecture": ("claude", "codex", "gemini", "kimi"),
    "fast_simple": ("kimi", "codex", "gemini", "claude"),
    "general": ("codex", "claude", "gemini", "kimi"),
}


def _extract_provider_telemetry(provider: str, telemetry: dict[str, Any] | None) -> dict[str, Any]:
    if not telemetry:
        return {}
    providers = telemetry.get("providers")
    if isinstance(providers, dict):
        data = providers.get(provider)
        return data if isinstance(data, dict) else {}
    data = telemetry.get(provider)
    return data if isinstance(data, dict) else {}


def _extract_critic_outcomes(
    provider: str,
    context_packet: dict[str, Any] | None,
    telemetry: dict[str, Any] | None,
) -> dict[str, Any]:
    for container in (telemetry, context_packet):
        if not isinstance(container, dict):
            continue
        outcomes = container.get("prior_critic_outcomes") or container.get("critic_outcomes")
        if isinstance(outcomes, dict):
            by_provider = outcomes.get("providers") if isinstance(outcomes.get("providers"), dict) else outcomes
            if isinstance(by_provider, dict):
                provider_outcomes = by_provider.get(provider)
                if isinstance(provider_outcomes, dict):
                    return provider_outcomes
                if provider in by_provider:
                    return {}
                return by_provider
    return {}


def _domain_fit(task_text: str) -> str:
    lowered = task_text.lower()
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw in lowered)
    best_domain = "general"
    best_score = 0
    for domain, score in scores.items():
        if score > best_score:
            best_score = score
            best_domain = domain
    if best_score <= 0:
        return "general"
    return best_domain


def _probe_provider(provider: str) -> tuple[bool, bool | None, str]:
    normalized_provider = str(provider).strip().lower()
    if normalized_provider == "claude":
        claude_bin = os.environ.get("OMG_CLAUDE_BIN", "claude")
        worker_cmd = os.environ.get("OMG_CLAUDE_WORKER_CMD", "").strip()
        if worker_cmd or shutil.which(claude_bin) is not None:
            return True, None, "cli-detected"
        return False, False, "provider CLI unavailable"

    if not is_canonical_parity_host(normalized_provider):
        return False, False, "unsupported provider"

    module_name = f"runtime.providers.{normalized_provider}_provider"
    try:
        _ = importlib.import_module(module_name)
    except Exception as exc:
        return False, False, f"provider module import failed: {exc}"

    cli_provider = get_provider(normalized_provider)
    if cli_provider is None:
        return False, False, "provider not registered"

    try:
        available = bool(cli_provider.detect())
    except Exception as exc:
        return False, None, f"provider detect failed: {exc}"

    if not available:
        return False, False, "provider CLI unavailable"

    auth_ok: bool | None
    try:
        auth_ok, _msg = cli_provider.check_auth()
    except Exception as exc:
        return True, None, f"auth check error: {exc}"
    return True, auth_ok, "ok"


def _score_provider(
    provider: str,
    domain_fit: str,
    context_packet: dict[str, Any] | None,
    telemetry: dict[str, Any] | None,
) -> tuple[float, list[str], bool]:
    available, auth_ok, status = _probe_provider(provider)
    reasons: list[str] = [status]
    score = 0.0

    ranked = _DOMAIN_PROVIDER_PREFS.get(domain_fit, _DOMAIN_PROVIDER_PREFS["general"])
    if provider in ranked:
        score += float(max(0, 5 - ranked.index(provider)))
        reasons.append(f"domain-rank={ranked.index(provider) + 1}")

    cost_tier = _COST_TIERS.get(provider, "high")
    score += float(_COST_SCORE.get(cost_tier, 0))
    reasons.append(f"cost={cost_tier}")

    if available:
        score += 3.0
        reasons.append("available")
    else:
        score -= 50.0
        reasons.append("unavailable")

    if auth_ok is True:
        score += 2.0
        reasons.append("auth-ok")
    elif auth_ok is False:
        score -= 8.0
        reasons.append("auth-failed")
    else:
        score -= 1.0
        reasons.append("auth-unknown")

    provider_telemetry = _extract_provider_telemetry(provider, telemetry)
    latency_ms = provider_telemetry.get("latency_ms")
    if isinstance(latency_ms, (int, float)):
        latency_penalty = min(5.0, float(latency_ms) / 250.0)
        score -= latency_penalty
        reasons.append(f"latency={int(latency_ms)}ms")

    failure_rate = provider_telemetry.get("failure_rate")
    if isinstance(failure_rate, (int, float)):
        fr = min(max(float(failure_rate), 0.0), 1.0)
        score -= fr * 6.0
        reasons.append(f"failure-rate={fr:.2f}")

    critic = _extract_critic_outcomes(provider, context_packet, telemetry)
    if critic:
        for critic_name in ("skeptic", "hallucination_auditor"):
            critic_result = critic.get(critic_name)
            if not isinstance(critic_result, dict):
                continue
            verdict = str(critic_result.get("verdict", "pass")).lower()
            if verdict == "fail":
                score -= 8.0
                reasons.append(f"{critic_name}=fail")
            elif verdict == "warn":
                score -= 3.0
                reasons.append(f"{critic_name}=warn")
            else:
                score += 0.5
                reasons.append(f"{critic_name}=pass")

    return score, reasons, available


def select_provider(
    task_text: str,
    project_dir: str,
    context_packet: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, str]:
    _ = project_dir
    domain_fit = _domain_fit(task_text)

    scored: list[tuple[str, float, list[str], bool]] = []
    for provider in _PROVIDERS:
        score, reasons, available = _score_provider(provider, domain_fit, context_packet, telemetry)
        scored.append((provider, score, reasons, available))

    scored.sort(key=lambda row: row[1], reverse=True)
    selected_provider, _score, selected_reasons, selected_available = scored[0]

    if not selected_available:
        selected_provider = "claude"
        selected_reasons = ["fallback=claude", *selected_reasons]

    return {
        "provider": selected_provider,
        "reason": "; ".join(selected_reasons[:5]),
        "cost_tier": _COST_TIERS.get(selected_provider, "high"),
        "domain_fit": domain_fit,
    }


__all__ = ["select_provider"]
