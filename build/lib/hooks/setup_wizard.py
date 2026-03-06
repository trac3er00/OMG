"""OMG Setup Wizard — CLI detection, MCP configuration, and preference bootstrap."""
from __future__ import annotations

import json
import logging
import os
from io import TextIOBase
from pathlib import Path
from typing import Any, cast

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from hooks._common import get_feature_flag
from runtime.cli_provider import get_provider, list_available_providers
from runtime.mcp_config_writers import (
    write_claude_mcp_config,
    write_codex_mcp_config,
    write_gemini_mcp_config,
    write_kimi_mcp_config,
)
from runtime.provider_bootstrap import (
    bootstrap_provider_hosts,
    collect_provider_status_with_options,
    normalize_provider_status_matrix,
)
import runtime.providers  # noqa: F401


_logger = logging.getLogger(__name__)

_INSTALL_HINTS: dict[str, str] = {
    "codex": "npm install -g @openai/codex",
    "gemini": "npm install -g @google/gemini-cli",
    "kimi": "uv tool install --python 3.13 kimi-cli",
}

def _write_cli_config(handle: TextIOBase, config: dict[str, Any]) -> None:
    if yaml is not None:
        yaml.safe_dump(config, handle, default_flow_style=False, sort_keys=False)
        return
    json.dump(config, handle, indent=2)
    handle.write("\n")


def _mcp_writers() -> dict[str, Any]:
    return {
        "codex": write_codex_mcp_config,
        "gemini": write_gemini_mcp_config,
        "kimi": write_kimi_mcp_config,
    }


def is_setup_enabled() -> bool:
    return get_feature_flag("SETUP", default=False)


def detect_clis() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name in list_available_providers():
        provider = get_provider(name)
        if provider is None:
            continue

        try:
            detected = provider.detect()
        except Exception as exc:
            _logger.warning("detect() failed for %s: %s", name, exc)
            detected = False

        auth_ok: bool | None = None
        message = ""
        if detected:
            try:
                auth_ok, message = provider.check_auth()
            except Exception as exc:
                _logger.warning("check_auth() failed for %s: %s", name, exc)
                message = f"Auth check error: {exc}"
        else:
            hint = _INSTALL_HINTS.get(name, f"Install the '{name}' CLI")
            message = f"Not found. Install: {hint}"

        results[name] = {"detected": detected, "auth_ok": auth_ok, "message": message}

    return results


def check_auth() -> dict[str, Any]:
    return {"status": "pending", "results": {}}


def configure_mcp(
    project_dir: str,
    detected_clis: dict[str, Any],
    server_url: str = "http://127.0.0.1:8765/mcp",
    server_name: str = "omg-memory",
) -> dict[str, Any]:
    configured: list[str] = []
    errors: dict[str, str] = {}
    written_paths: list[str] = []

    write_claude_mcp_config(project_dir, server_url, server_name)
    written_paths.append(str(Path(project_dir) / ".mcp.json"))

    for cli_name, writer in _mcp_writers().items():
        cli_info = detected_clis.get(cli_name)
        if not isinstance(cli_info, dict) or not cli_info.get("detected", False):
            continue

        try:
            writer_result = writer(server_url, server_name)
            configured.append(cli_name)
            if isinstance(writer_result, dict):
                config_path = writer_result.get("config_path")
                if isinstance(config_path, str) and config_path:
                    written_paths.append(config_path)
            elif cli_name == "gemini":
                written_paths.append(str(Path.home() / ".gemini" / "settings.json"))
            elif cli_name == "kimi":
                written_paths.append(str(Path.home() / ".kimi" / "mcp.json"))
        except Exception as exc:
            errors[cli_name] = str(exc)

    return {
        "status": "ok",
        "configured": configured,
        "errors": errors,
        "written_paths": written_paths,
    }


def set_preferences(project_dir: str, preferences: dict[str, Any]) -> dict[str, Any]:
    default_cli_configs: dict[str, Any] = {
        "codex": {"subscription": "free", "max_parallel_agents": 1},
        "gemini": {"subscription": "free", "max_parallel_agents": 1},
        "kimi": {"subscription": "free", "max_parallel_agents": 1},
    }
    default_config: dict[str, Any] = {
        "version": "2.0",
        "cli_configs": default_cli_configs,
    }

    if preferences and isinstance(preferences, dict):
        cli_configs = preferences.get("cli_configs")
        if isinstance(cli_configs, dict):
            default_cli_configs.update(cast(dict[str, Any], cli_configs))

    state_dir = os.path.join(project_dir, ".omg", "state")
    os.makedirs(state_dir, exist_ok=True)

    config_path = os.path.join(state_dir, "cli-config.yaml")
    with open(config_path, "w", encoding="utf-8") as handle:
        _write_cli_config(handle, default_config)

    return {"status": "ok", "path": config_path, "config": default_config}


def run_setup_wizard(project_dir: str, non_interactive: bool = False) -> dict[str, Any]:
    if not is_setup_enabled():
        return {
            "status": "disabled",
            "message": "Setup wizard disabled. Set OMG_SETUP_ENABLED=1 to enable.",
        }

    clis = detect_clis()
    auth = check_auth()
    mcp = configure_mcp(project_dir, clis)
    provider_bootstrap = bootstrap_provider_hosts(project_dir)
    provider_status = normalize_provider_status_matrix(
        project_dir,
        collect_provider_status_with_options(project_dir, include_smoke=False),
    )
    prefs = set_preferences(project_dir, {})

    return {
        "status": "complete",
        "non_interactive": non_interactive,
        "clis_detected": clis,
        "auth_status": auth,
        "mcp_configured": mcp,
        "provider_bootstrap": provider_bootstrap,
        "provider_status": provider_status,
        "preferences": prefs,
    }
