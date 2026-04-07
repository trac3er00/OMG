"""Runtime profile loading and parallelism budgets."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict, cast

import yaml

from .adoption import CANONICAL_MODE_NAMES


_logger = logging.getLogger(__name__)


class RuntimeProfile(TypedDict):
    profile: str
    max_workers: int | None
    background_polling: bool
    description: str


class CanonicalModeProfile(TypedDict):
    concurrency: int
    background_verification: bool
    context_window: str
    noise_level: str


PROFILE_PRESETS: dict[str, RuntimeProfile] = {
    "eco": {
        "profile": "eco",
        "max_workers": 2,
        "background_polling": False,
        "description": "Low-cost fixed concurrency",
    },
    "balanced": {
        "profile": "balanced",
        "max_workers": 3,
        "background_polling": False,
        "description": "Default fixed concurrency",
    },
    "turbo": {
        "profile": "turbo",
        "max_workers": 5,
        "background_polling": True,
        "description": "Higher fixed concurrency",
    },
    "elastic": {
        "profile": "elastic",
        "max_workers": None,
        "background_polling": True,
        "description": "Auto-scaling based on task complexity and budget",
    },
}

RUNTIME_CONCURRENCY_PROFILE_NAMES = tuple(PROFILE_PRESETS.keys())
RESERVED_CANONICAL_MODE_NAMES = CANONICAL_MODE_NAMES

_CANONICAL_MODE_PROFILES: dict[str, CanonicalModeProfile] = {
    "chill": {
        "concurrency": 1,
        "background_verification": False,
        "context_window": "minimal",
        "noise_level": "quiet",
    },
    "focused": {
        "concurrency": 2,
        "background_verification": False,
        "context_window": "standard",
        "noise_level": "normal",
    },
    "exploratory": {
        "concurrency": 4,
        "background_verification": True,
        "context_window": "extended",
        "noise_level": "verbose",
    },
}


def load_canonical_mode_profile(mode: str) -> dict[str, object]:
    normalized_mode = mode.strip().lower()
    profile = _CANONICAL_MODE_PROFILES.get(normalized_mode)
    if profile is None:
        raise ValueError(
            f"Unknown canonical mode: {mode!r}. Valid: chill, focused, exploratory"
        )
    return dict(profile)


def load_runtime_profile(project_dir: str) -> RuntimeProfile:
    runtime_path = Path(project_dir) / ".omg" / "runtime.yaml"
    profile_name = "balanced"
    if runtime_path.exists():
        try:
            raw_payload: object = (
                yaml.safe_load(runtime_path.read_text(encoding="utf-8")) or {}
            )
        except Exception as exc:
            _logger.debug(
                "Failed to parse runtime profile from %s: %s",
                runtime_path,
                exc,
                exc_info=True,
            )
            raw_payload = {}
        if isinstance(raw_payload, dict):
            payload_map = cast(dict[object, object], raw_payload)
            payload: dict[str, object] = {}
            for key, value in payload_map.items():
                if isinstance(key, str):
                    payload[key] = value
            candidate_obj = payload.get("profile", profile_name)
            candidate = (
                candidate_obj.strip()
                if isinstance(candidate_obj, str)
                else profile_name
            )
            if candidate in RUNTIME_CONCURRENCY_PROFILE_NAMES:
                profile_name = candidate

    preset = PROFILE_PRESETS[profile_name]
    result: RuntimeProfile = {
        "profile": preset["profile"],
        "max_workers": preset["max_workers"],
        "background_polling": preset["background_polling"],
        "description": preset["description"],
    }
    return result


def resolve_parallel_workers(project_dir: str, *, requested_workers: int) -> int:
    profile = load_runtime_profile(project_dir)
    raw_max_workers = profile["max_workers"]
    max_workers = (
        int(raw_max_workers) if raw_max_workers is not None else requested_workers
    )
    cli_cap = _load_cli_parallel_cap(project_dir)
    if cli_cap is not None:
        max_workers = min(max_workers, cli_cap)
    return max(1, min(requested_workers, max_workers))


def _load_cli_parallel_cap(project_dir: str) -> int | None:
    config_path = Path(project_dir) / ".omg" / "state" / "cli-config.yaml"
    if not config_path.exists():
        return None
    try:
        raw_payload: object = (
            yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        )
    except Exception as exc:
        _logger.debug(
            "Failed to parse CLI parallel cap from %s: %s",
            config_path,
            exc,
            exc_info=True,
        )
        return None
    if not isinstance(raw_payload, dict):
        return None

    payload_map = cast(dict[object, object], raw_payload)
    payload: dict[str, object] = {}
    for key, value in payload_map.items():
        if isinstance(key, str):
            payload[key] = value

    cli_configs_obj = payload.get("cli_configs")
    if not isinstance(cli_configs_obj, dict):
        return None

    cli_configs = cast(dict[object, object], cli_configs_obj)
    caps: list[int] = []
    for config in cli_configs.values():
        if not isinstance(config, dict):
            continue
        config_map = cast(dict[object, object], config)
        value = config_map.get("max_parallel_agents")
        if isinstance(value, int) and value > 0:
            caps.append(value)
    return min(caps) if caps else None
