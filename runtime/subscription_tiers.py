from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from runtime.canonical_taxonomy import SUBSCRIPTION_TIERS


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TierSpec:
    budget_usd_per_session: float
    max_parallel_agents: int
    features: tuple[str, ...]


class TierDetectionResult(TypedDict):
    tier: str
    provenance: str
    confidence: float
    budget_usd_per_session: float
    max_parallel_agents: int
    reason: NotRequired[str]


TIER_REGISTRY: dict[str, TierSpec] = {
    "free": TierSpec(
        budget_usd_per_session=5.0,
        max_parallel_agents=1,
        features=("baseline",),
    ),
    "pro": TierSpec(
        budget_usd_per_session=20.0,
        max_parallel_agents=3,
        features=("baseline", "higher_budget"),
    ),
    "max": TierSpec(
        budget_usd_per_session=100.0,
        max_parallel_agents=5,
        features=("baseline", "higher_budget", "extended_context"),
    ),
    "team": TierSpec(
        budget_usd_per_session=50.0,
        max_parallel_agents=8,
        features=("baseline", "collaboration", "higher_budget"),
    ),
    "enterprise_tier": TierSpec(
        budget_usd_per_session=200.0,
        max_parallel_agents=20,
        features=("baseline", "collaboration", "governance_plus"),
    ),
}

_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
_PLAN_ENV_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    "claude": ("ANTHROPIC_PLAN",),
    "codex": ("CODEX_PLAN", "OPENAI_PLAN"),
    "openai": ("OPENAI_PLAN",),
    "gemini": ("GEMINI_PLAN",),
    "kimi": ("KIMI_PLAN",),
}


def detect_tier(provider: str, *, project_dir: str | None = None) -> TierDetectionResult:
    reasons: list[str] = []
    normalized_provider = (provider or "").strip().lower() or "unknown"

    try:
        provider_tier = _detect_provider_tier(normalized_provider)
    except Exception as exc:
        provider_tier = None
        reasons.append(str(exc) or "provider_api_failed")

    if provider_tier:
        result = _build_result(provider_tier, "provider_api", 0.95, reasons)
        _write_tier_cache(normalized_provider, provider_tier)
        return result

    local_tier = _detect_local_tier(normalized_provider, project_dir)
    if local_tier:
        result = _build_result(local_tier, "local_config", 0.80, reasons)
        _write_tier_cache(normalized_provider, local_tier)
        return result

    cached_tier = _read_cached_tier(normalized_provider)
    if cached_tier:
        return _build_result(cached_tier, "cache", 0.65, reasons)

    return _build_result("free", "default", 0.40, reasons)


def _build_result(tier: str, provenance: str, confidence: float, reasons: list[str]) -> TierDetectionResult:
    normalized_tier = _normalize_tier_value(tier) or "free"
    spec = TIER_REGISTRY[normalized_tier]
    result: TierDetectionResult = {
        "tier": normalized_tier,
        "provenance": provenance,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "budget_usd_per_session": spec.budget_usd_per_session,
        "max_parallel_agents": spec.max_parallel_agents,
    }
    if reasons:
        result["reason"] = "; ".join(reason for reason in reasons if reason)
    return result


def _detect_provider_tier(provider: str) -> str | None:
    keys = _PLAN_ENV_BY_PROVIDER.get(provider, ())
    if not keys:
        keys = ("ANTHROPIC_PLAN", "CODEX_PLAN", "OPENAI_PLAN", "GEMINI_PLAN", "KIMI_PLAN")

    for key in keys:
        error_key = f"{key}_ERROR"
        error_value = os.environ.get(error_key, "").strip()
        if error_value:
            raise RuntimeError(f"provider_api: {error_value}")

        value = os.environ.get(key, "").strip()
        if value:
            normalized = _normalize_tier_value(value)
            if normalized:
                return normalized

    return None


def _detect_local_tier(provider: str, project_dir: str | None) -> str | None:
    from_env = _normalize_tier_value(os.environ.get("OMG_SUBSCRIPTION_TIER", ""))
    if from_env:
        return from_env

    root = Path(project_dir) if project_dir else Path.cwd()
    settings_tier = _read_settings_tier(root)
    if settings_tier:
        return settings_tier

    cli_tier = _read_cli_config_tier(root, provider)
    if cli_tier:
        return cli_tier

    return None


def _read_settings_tier(project_root: Path) -> str | None:
    settings_path = project_root / "settings.json"
    if not settings_path.exists():
        return None
    try:
        raw_obj = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger.debug("Failed to parse settings tier from %s: %s", settings_path, exc, exc_info=True)
        return None

    if not isinstance(raw_obj, dict):
        return None
    raw = cast(dict[str, object], raw_obj)

    omg_cfg = raw.get("_omg")
    if not isinstance(omg_cfg, dict):
        return None
    maybe = omg_cfg.get("subscription_tier")
    return _normalize_tier_value(maybe)


def _read_cli_config_tier(project_root: Path, provider: str) -> str | None:
    config_path = project_root / ".omg" / "state" / "cli-config.yaml"
    if not config_path.exists():
        return None

    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        _logger.debug("Failed to read CLI tier config from %s: %s", config_path, exc, exc_info=True)
        return None

    in_provider_block = False
    provider_indent = ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.endswith(":") and stripped[:-1].strip() == provider:
            in_provider_block = True
            provider_indent = line[: len(line) - len(line.lstrip())]
            continue

        if in_provider_block:
            if stripped.endswith(":") and not line.startswith(provider_indent + "  "):
                in_provider_block = False
                continue
            if stripped.startswith("subscription:"):
                _, _, value = stripped.partition(":")
                return _normalize_tier_value(value.strip())

    return None


def _tier_cache_path() -> Path:
    return Path.home() / ".omg" / "state" / "tier-cache.json"


def _read_cached_tier(provider: str) -> str | None:
    path = _tier_cache_path()
    if not path.exists():
        return None

    try:
        payload_obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger.debug("Failed to read tier cache from %s: %s", path, exc, exc_info=True)
        return None

    if not isinstance(payload_obj, dict):
        return None
    payload = cast(dict[str, object], payload_obj)

    cache_ts = payload.get("timestamp")
    if not isinstance(cache_ts, (int, float)):
        return None

    age = time.time() - float(cache_ts)
    if age > _CACHE_MAX_AGE_SECONDS:
        return None

    cache_provider_raw = payload.get("provider", "")
    cache_provider = str(cache_provider_raw).strip().lower()
    if cache_provider and cache_provider != provider:
        return None

    return _normalize_tier_value(payload.get("tier"))


def _write_tier_cache(provider: str, tier: str) -> None:
    path = _tier_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "tier": tier,
        "timestamp": time.time(),
    }
    try:
        _ = path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    except Exception as exc:
        _logger.debug("Failed to write tier cache to %s: %s", path, exc, exc_info=True)
        return


def _normalize_tier_value(raw: object) -> str | None:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    aliases = {
        "enterprise": "enterprise_tier",
        "enterprise-tier": "enterprise_tier",
        "max_200": "max",
        "max-200": "max",
    }
    value = aliases.get(value, value)
    if value in TIER_REGISTRY:
        return value
    return None


if set(TIER_REGISTRY.keys()) != set(SUBSCRIPTION_TIERS):
    raise ValueError("TIER_REGISTRY must exactly match SUBSCRIPTION_TIERS")
