"""Runtime profile loading and parallelism budgets."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "eco": {"profile": "eco", "max_workers": 2, "background_polling": False},
    "balanced": {"profile": "balanced", "max_workers": 3, "background_polling": False},
    "turbo": {"profile": "turbo", "max_workers": 5, "background_polling": True},
}


def load_runtime_profile(project_dir: str) -> dict[str, Any]:
    runtime_path = Path(project_dir) / ".omg" / "runtime.yaml"
    profile_name = "balanced"
    if runtime_path.exists():
        try:
            payload = yaml.safe_load(runtime_path.read_text(encoding="utf-8")) or {}
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            candidate = str(payload.get("profile", profile_name)).strip()
            if candidate in PROFILE_PRESETS:
                profile_name = candidate
    return dict(PROFILE_PRESETS[profile_name])


def resolve_parallel_workers(project_dir: str, *, requested_workers: int) -> int:
    profile = load_runtime_profile(project_dir)
    max_workers = int(profile["max_workers"])
    cli_cap = _load_cli_parallel_cap(project_dir)
    if cli_cap is not None:
        max_workers = min(max_workers, cli_cap)
    return max(1, min(requested_workers, max_workers))


def _load_cli_parallel_cap(project_dir: str) -> int | None:
    config_path = Path(project_dir) / ".omg" / "state" / "cli-config.yaml"
    if not config_path.exists():
        return None
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    cli_configs = payload.get("cli_configs", {})
    if not isinstance(cli_configs, dict):
        return None
    caps = []
    for config in cli_configs.values():
        if not isinstance(config, dict):
            continue
        value = config.get("max_parallel_agents")
        if isinstance(value, int) and value > 0:
            caps.append(value)
    return min(caps) if caps else None
