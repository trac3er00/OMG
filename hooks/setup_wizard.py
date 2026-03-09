"""OMG Setup Wizard — interactive CLI detection, auth verification, and MCP configuration.

Feature-gated: requires OMG_SETUP_ENABLED=1 (default off).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any, cast

import yaml

from hooks._common import get_feature_flag

# Ensure project root is on sys.path for runtime imports
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from runtime.cli_provider import get_provider, list_available_providers  # noqa: E402
from runtime.mcp_config_writers import (  # noqa: E402
    write_claude_mcp_config,
    write_claude_mcp_stdio_config,
    write_codex_mcp_config,
    write_codex_mcp_stdio_config,
    write_gemini_mcp_config,
    write_gemini_mcp_stdio_config,
    write_kimi_mcp_config,
    write_kimi_mcp_stdio_config,
)

# Trigger provider auto-registration on import
import runtime.providers.codex_provider  # noqa: E402, F401
import runtime.providers.gemini_provider  # noqa: E402, F401
import runtime.providers.kimi_provider  # noqa: E402, F401
from runtime.adoption import (  # noqa: E402
    CANONICAL_MODE_NAMES,
    CANONICAL_VERSION,
    build_adoption_report,
    get_mode_profile,
    get_preset_features,
    resolve_preset,
    write_adoption_report,
)

_logger = logging.getLogger(__name__)

OMG_CONTROL_COMMAND = "python3"
OMG_CONTROL_ARGS = ["-m", "runtime.omg_mcp_server"]
OMG_CONTROL_SERVER_NAME = "omg-control"

_INSTALL_HINTS: dict[str, str] = {
    "codex": "npm install -g @openai/codex",
    "gemini": "npm install -g @google/gemini-cli",
    "kimi": "uv tool install --python 3.13 kimi-cli",
}

BYPASS_ALL_WARNING = (
    "⚠️  BYPASS-ALL / FULL VIBE-CODE MODE WARNING ⚠️\n\n"
    "Enabling bypass-all grants Claude Code unrestricted write access to your filesystem "
    "without asking for confirmation on individual file edits.\n\n"
    "IMPORTANT DISCLAIMER: The author takes NO responsibility for any data loss, "
    "unintended file modifications, or system changes that occur while bypass-all is enabled. "
    "Use at your own risk.\n\n"
    "Note: Some safety measures remain active even in bypass-all mode:\n"
    "  • Firewall deny rules still block dangerous commands (rm -rf, sudo, etc.)\n"
    "  • Secret-guard still protects credentials and API keys\n"
    "  • You can disable bypass-all at any time via settings.json\n\n"
    "Do you want to enable bypass-all mode? (y/N): "
)

PRESET_ORDER: tuple[str, ...] = ("safe", "balanced", "interop", "labs")
_PRESET_LEVEL: dict[str, int] = {p: i for i, p in enumerate(PRESET_ORDER)}

MCP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "Upstash Context7 MCP server for context management",
        "command": "npx",
        "args": ["@upstash/context7-mcp@2.1.3"],
        "default": False,
        "min_preset": "balanced",
        "category": "productivity",
    },
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "ModelContextProtocol filesystem server for file operations",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."],
        "default": True,
        "min_preset": "safe",
        "category": "system",
    },
    {
        "id": "websearch",
        "name": "Web Search",
        "description": "Web search MCP server for internet queries",
        "command": "npx",
        "args": ["@zhafron/mcp-web-search@1.2.2"],
        "default": False,
        "min_preset": "interop",
        "category": "search",
    },
    {
        "id": "chrome-devtools",
        "name": "Chrome DevTools",
        "description": "Chrome DevTools MCP server for browser automation",
        "command": "npx",
        "args": ["chrome-devtools-mcp@0.19.0"],
        "default": False,
        "min_preset": "labs",
        "category": "browser",
    },
    {
        "id": "omg-memory",
        "name": "OMG Memory",
        "description": "OMG shared memory server via HTTP",
        "command": None,
        "args": [],
        "type": "http",
        "url": "http://127.0.0.1:8765/mcp",
        "default": False,
        "min_preset": "interop",
        "category": "memory",
    },
    {
        "id": OMG_CONTROL_SERVER_NAME,
        "name": "OMG Control",
        "description": "OMG control plane MCP server via stdio",
        "command": OMG_CONTROL_COMMAND,
        "args": OMG_CONTROL_ARGS,
        "default": True,
        "min_preset": "safe",
        "category": "control",
    },
    {
        "id": "github",
        "name": "GitHub",
        "description": "ModelContextProtocol GitHub server for repository operations",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-github"],
        "default": False,
        "category": "vcs",
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "ModelContextProtocol Puppeteer server for browser automation",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-puppeteer"],
        "default": False,
        "category": "browser",
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "ModelContextProtocol Brave Search server",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-brave-search"],
        "default": False,
        "category": "search",
    },
    {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "description": "ModelContextProtocol Sequential Thinking server for reasoning",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-sequential-thinking"],
        "default": False,
        "category": "reasoning",
    },
    {
        "id": "grep-app",
        "name": "Grep App",
        "description": "Grep App MCP server for code search",
        "command": "npx",
        "args": ["grep-app-mcp"],
        "default": False,
        "category": "search",
    },
    {
        "id": "memory-graph",
        "name": "Memory Graph",
        "description": "ModelContextProtocol Memory server for knowledge graphs",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-memory"],
        "default": False,
        "category": "memory",
    },
]

_MCP_ID_ALIASES: dict[str, str] = {
    "file-system": "filesystem",
    "file_system": "filesystem",
    "grep": "grep-app",
    "grep_app": "grep-app",
}


def get_mcp_catalog() -> list[dict[str, Any]]:
    """Return the MCP catalog.

    Returns:
        List of MCP server definitions with id, name, description, command, args, default, and category.
    """
    return MCP_CATALOG


def get_default_mcps_for_preset(preset: str) -> list[str]:
    """Return the list of MCP server IDs enabled by default for *preset*.

    Each catalog entry carries a ``min_preset`` field that specifies the
    lowest preset tier at which the MCP is included.  The preset order is
    ``safe < balanced < interop < labs``.

    Returns:
        Sorted list of MCP server IDs whose ``min_preset`` is at or below
        the requested *preset* level.
    """
    level = _PRESET_LEVEL.get(preset, 0)
    return [
        m["id"]
        for m in MCP_CATALOG
        if _PRESET_LEVEL.get(m.get("min_preset", ""), -1) <= level
        and m.get("min_preset") is not None
    ]


def _normalize_mcp_ids(selected_ids: list[str]) -> list[str]:
    valid_ids = {cast(str, m["id"]) for m in MCP_CATALOG}
    normalized_ids: list[str] = []
    seen: set[str] = set()
    unknown_ids: list[str] = []

    for raw_id in selected_ids:
        normalized = _MCP_ID_ALIASES.get(raw_id, raw_id)
        if normalized not in valid_ids:
            unknown_ids.append(raw_id)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_ids.append(normalized)

    if unknown_ids:
        raise ValueError(
            "Unsupported MCP server IDs: " + ", ".join(unknown_ids)
        )

    return normalized_ids


def build_mcp_config(selected_ids: list[str]) -> dict[str, Any]:
    """Build .mcp.json configuration from selected MCP server IDs.

    Args:
        selected_ids: List of MCP server IDs to include in the config.

    Returns:
        Dict with 'mcpServers' key containing the MCP server configurations.
    """
    normalized_ids = _normalize_mcp_ids(selected_ids)
    mcp_servers: dict[str, Any] = {}

    for mcp in MCP_CATALOG:
        if mcp["id"] not in normalized_ids:
            continue

        mcp_id = mcp["id"]

        # HTTP-type MCPs (like omg-memory)
        if mcp.get("type") == "http":
            mcp_servers[mcp_id] = {
                "type": "http",
                "url": mcp["url"],
            }
        # NPX-type MCPs
        else:
            mcp_servers[mcp_id] = {
                "command": mcp["command"],
                "args": mcp["args"],
            }

    return {"mcpServers": mcp_servers}


def configure_plan_type(plan_type: str) -> dict[str, Any]:
    """Configure Claude plan type and model routing.

    Args:
        plan_type: "max" or "pro"

    Returns:
        dict with plan_type and optionally model_routing
    """
    result: dict[str, Any] = {"plan_type": plan_type}
    if plan_type == "pro":
        result["model_routing"] = {
            "planning": "claude-opus-4-5",
            "coding": "claude-sonnet-4-5",
            "review": "claude-opus-4-5",
            "commit": "claude-haiku-4-5",
        }
    return result


def select_mcps(selected_ids: list[str] | None = None, preset: str = "safe") -> dict[str, Any]:
    """Build MCP config from selected IDs.

    Args:
        selected_ids: List of MCP IDs to include. If None, uses preset defaults.
        preset: Preset tier that controls which MCPs are included by default.

    Returns:
        dict with mcpServers key (ready to write as .mcp.json)
    """
    if selected_ids is None:
        selected_ids = get_default_mcps_for_preset(preset)
    else:
        selected_ids = _normalize_mcp_ids(selected_ids)
    return build_mcp_config(selected_ids)


def configure_bypass_all(enabled: bool) -> dict[str, Any]:
    """Configure bypass_all mode.

    Args:
        enabled: True to enable bypass-all, False to disable

    Returns:
        dict with enabled status and warning_shown flag
    """
    result: dict[str, Any] = {"enabled": enabled}
    if enabled:
        result["warning_shown"] = True
    return result


def is_setup_enabled() -> bool:
    """Check if the setup wizard feature is enabled.

    Uses get_feature_flag("SETUP", default=False) — disabled by default.
    Enable via OMG_SETUP_ENABLED=1 env var or settings.json._omg.features.SETUP: true.
    """
    return get_feature_flag("SETUP", default=False)


def detect_clis() -> dict[str, Any]:
    """Detect installed CLI tools using the provider registry.

    Iterates over all registered providers, calling ``detect()`` and
    ``check_auth()`` on each.  Returns a dict keyed by provider name::

        {
            "codex": {"detected": True, "auth_ok": True, "message": "..."},
            "gemini": {"detected": False, "auth_ok": None,
                       "message": "Not found. Install: npm install -g @google/gemini-cli"},
            ...
        }
    """
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
                auth_ok = None
                message = f"Auth check error: {exc}"
        else:
            hint = _INSTALL_HINTS.get(name, f"Install the '{name}' CLI")
            message = f"Not found. Install: {hint}"

        results[name] = {
            "detected": detected,
            "auth_ok": auth_ok,
            "message": message,
        }

    return results


def get_cli_auth_instructions(provider: str) -> dict[str, str]:
    """Return install, auth, and verify instructions for a CLI provider.

    This function returns command strings only — it does NOT execute anything
    or store credentials.

    Args:
        provider: CLI provider name (e.g. "codex", "gemini", or "kimi").

    Returns:
        Dict with keys: install, auth, verify, subscription.
        Unknown providers return placeholder strings.
    """
    instructions: dict[str, dict[str, str]] = {
        "codex": {
            "install": "npm install -g @openai/codex",
            "auth": "codex login",
            "verify": "codex --version",
            "subscription": "Requires ChatGPT Plus, Team, or Enterprise subscription (or OpenAI API key)",
        },
        "gemini": {
            "install": "npm install -g @google/gemini-cli",
            "auth": "gemini auth login",
            "verify": "gemini --version",
            "subscription": "Requires Google account with Gemini API access (free tier available)",
        },
        "kimi": {
            "install": "uv tool install --python 3.13 kimi-cli",
            "auth": "Add token to ~/.kimi/config.toml",
            "verify": "kimi --version",
            "subscription": "Requires Kimi API key from platform.moonshot.cn",
        },
    }

    return instructions.get(provider, {
        "install": "Unknown provider",
        "auth": "Unknown provider",
        "verify": "Unknown provider",
        "subscription": "Unknown",
    })


def check_auth() -> dict[str, Any]:
    """Verify authentication for detected CLI tools.

    Stub — returns pending status. T16 will implement real auth checks
    using each provider's check_auth() method.
    """
    return {"status": "pending", "results": {}}


_HTTP_MEMORY_MIN_LEVEL: int = _PRESET_LEVEL["interop"]

_PROFILE_ARCH_REQUEST_MAX = 8
_PROFILE_TAG_MAX = 12
_PROFILE_SUMMARY_MAX_CHARS = 240
_PROFILE_RECENT_UPDATES_MAX = 5


def get_mode_choices() -> list[str]:
    return list(CANONICAL_MODE_NAMES)


def select_setup_mode(mode: str | None) -> str:
    candidate = (mode or "").strip().lower()
    if candidate in CANONICAL_MODE_NAMES:
        return candidate
    return "focused"


def configure_mcp(
    project_dir: str,
    detected_clis: dict[str, Any],
    server_url: str = "http://127.0.0.1:8765/mcp",
    server_name: str = "omg-memory",
    control_command: str = OMG_CONTROL_COMMAND,
    control_args: list[str] | None = None,
    control_server_name: str = OMG_CONTROL_SERVER_NAME,
    preset: str = "safe",
    selected_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Configure OMG MCP servers for authenticated CLIs.

    For each CLI in detected_clis where detected_clis[cli]["detected"] == True,
    calls the appropriate writer from runtime.mcp_config_writers.

    HTTP memory surfaces are only written when the *preset* is at or above
    ``interop`` level.  ``safe`` and ``balanced`` presets write only the
    stdio ``omg-control`` surface.

    Args:
        project_dir: Path to the project directory.
        detected_clis: Dict of CLI detection results from detect_clis().
        server_url: MCP server URL (default: http://127.0.0.1:8765/mcp).
        server_name: MCP server name (default: omg-memory).
        control_command: stdio command for the OMG control MCP server.
        control_args: stdio args for the OMG control MCP server.
        control_server_name: MCP server name for the OMG control surface.
        preset: Active preset tier (safe, balanced, interop, labs).

    Returns:
        Dict with keys:
        - status: "ok" on success
        - configured: List of CLI names that were successfully configured
        - errors: Dict of CLI name → error message for failures
    """
    configured: list[str] = []
    errors: dict[str, str] = {}
    resolved_control_args = list(control_args or OMG_CONTROL_ARGS)
    http_memory_allowed = _PRESET_LEVEL.get(preset, 0) >= _HTTP_MEMORY_MIN_LEVEL
    selected_config = select_mcps(selected_ids=selected_ids, preset=preset)
    selected_servers = cast(
        dict[str, dict[str, Any]],
        selected_config.get("mcpServers", {}),
    )

    try:
        config_path = os.path.join(project_dir, ".mcp.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                claude_config = json.load(f)
            if not isinstance(claude_config, dict):
                claude_config = {}
        else:
            claude_config = {}

        existing_servers = claude_config.get("mcpServers")
        if not isinstance(existing_servers, dict):
            existing_servers = {}

        managed_server_ids = {cast(str, m["id"]) for m in MCP_CATALOG}
        for managed_server_id in managed_server_ids:
            existing_servers.pop(managed_server_id, None)
        existing_servers.pop(server_name, None)
        existing_servers.pop(control_server_name, None)

        for selected_server_name, payload in selected_servers.items():
            if selected_server_name == "omg-memory":
                if not http_memory_allowed:
                    continue
                target_name = server_name
                payload = {"type": "http", "url": server_url}
            elif selected_server_name == OMG_CONTROL_SERVER_NAME:
                target_name = control_server_name
                payload = {
                    "command": control_command,
                    "args": resolved_control_args,
                }
            else:
                target_name = selected_server_name
            existing_servers[target_name] = payload

        claude_config["mcpServers"] = existing_servers
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(claude_config, f, indent=2, ensure_ascii=True)
            f.write("\n")
    except Exception as exc:
        _logger.warning("Failed to write Claude MCP config: %s", exc)
        errors["claude"] = str(exc)

    cli_writers = {
        "codex": (write_codex_mcp_config, write_codex_mcp_stdio_config),
        "gemini": (write_gemini_mcp_config, write_gemini_mcp_stdio_config),
        "kimi": (write_kimi_mcp_config, write_kimi_mcp_stdio_config),
    }

    for cli_name, (http_writer, stdio_writer) in cli_writers.items():
        cli_info = detected_clis.get(cli_name, {})
        if not cli_info.get("detected", False):
            continue

        try:
            for selected_server_name, payload in selected_servers.items():
                if selected_server_name == "omg-memory":
                    if not http_memory_allowed:
                        continue
                    http_writer(server_url, server_name)
                    continue

                if selected_server_name == OMG_CONTROL_SERVER_NAME:
                    stdio_writer(
                        command=control_command,
                        args=resolved_control_args,
                        server_name=control_server_name,
                    )
                    continue

                if payload.get("type") == "http":
                    http_writer(cast(str, payload["url"]), selected_server_name)
                    continue

                stdio_writer(
                    command=cast(str, payload["command"]),
                    args=[str(arg) for arg in cast(list[Any], payload.get("args", []))],
                    server_name=selected_server_name,
                )
            configured.append(cli_name)
        except Exception as exc:
            _logger.warning("Failed to write %s MCP config: %s", cli_name, exc)
            errors[cli_name] = str(exc)

    return {
        "status": "ok",
        "configured": configured,
        "errors": errors,
    }


def set_preferences(project_dir: str, preferences: dict[str, Any]) -> dict[str, Any]:
    """Set user preferences for CLI routing and save to .omg/state/cli-config.yaml.

    Args:
        project_dir: Path to the project directory.
        preferences: Dict with optional 'cli_configs' key. If empty, uses defaults.
                    Expected structure:
                    {
                        "cli_configs": {
                            "codex": {"subscription": "free", "max_parallel_agents": 1},
                            "gemini": {"subscription": "free", "max_parallel_agents": 1},
                            ...
                        }
                    }

    Returns:
        Dict with keys:
        - status: "ok" on success
        - path: Full path to saved config file
        - config: The saved config dict (version + cli_configs)
    """
    # Default config structure
    default_cli_configs: dict[str, Any] = {
        "codex": {"subscription": "free", "max_parallel_agents": 1},
        "gemini": {"subscription": "free", "max_parallel_agents": 1},
        "kimi": {"subscription": "free", "max_parallel_agents": 1},
    }
    preset = resolve_preset(cast(str | None, preferences.get("preset")))
    default_config: dict[str, Any] = {
        "version": CANONICAL_VERSION,
        "preset": preset,
        "resolved_features": get_preset_features(preset),
        "cli_configs": default_cli_configs,
        "selected_mcps": get_default_mcps_for_preset(preset),
        "browser_capability": {"enabled": False},
    }

    # Merge custom preferences if provided
    if preferences and isinstance(preferences, dict):
        cli_configs = preferences.get("cli_configs")
        if isinstance(cli_configs, dict):
            default_cli_configs.update(cast(dict[str, Any], cli_configs))
        selected_mcps = preferences.get("selected_mcps")
        if isinstance(selected_mcps, list):
            default_config["selected_mcps"] = _normalize_mcp_ids(
                [str(item) for item in selected_mcps]
            )
        browser_capability = preferences.get("browser_capability")
        if isinstance(browser_capability, dict):
            default_config["browser_capability"] = {
                "enabled": bool(browser_capability.get("enabled", False))
            }

    _write_project_settings_preset(project_dir, preset)

    # Create .omg/state directory if needed
    state_dir = os.path.join(project_dir, ".omg", "state")
    os.makedirs(state_dir, exist_ok=True)

    _write_profile_learning_sections(state_dir, preferences)

    # Write config to YAML file
    config_path = os.path.join(state_dir, "cli-config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

    _logger.info("Saved CLI config to %s", config_path)

    return {
        "status": "ok",
        "path": config_path,
        "config": default_config,
    }


def _write_profile_learning_sections(state_dir: str, preferences: dict[str, Any]) -> None:
    profile_path = os.path.join(state_dir, "profile.yaml")
    profile_data = _load_profile_yaml(profile_path)
    _ensure_profile_baseline(profile_data)

    profile_data["preferences"] = _normalize_preferences_block(preferences.get("preferences"))
    profile_data["user_vector"] = _normalize_user_vector_block(preferences.get("user_vector"))
    profile_data["profile_provenance"] = _normalize_provenance_block(preferences.get("profile_provenance"))

    from runtime.profile_io import save_profile
    save_profile(profile_path, profile_data)


def _render_explicit_empty_collections(dumped: str) -> str:
    lines = dumped.splitlines()
    output: list[str] = []

    def _next_line(start: int) -> str:
        if start + 1 < len(lines):
            return lines[start + 1]
        return ""

    for idx, line in enumerate(lines):
        next_line = _next_line(idx)
        stripped = line.strip()

        if stripped == "stack:" and (not next_line or not next_line.startswith("- ")):
            output.append("stack: []")
            continue
        if stripped == "conventions:" and (not next_line or not next_line.startswith("  ")):
            output.append("conventions: {}")
            continue
        if stripped == "ai_behavior:" and (not next_line or not next_line.startswith("  ")):
            output.append("ai_behavior: {}")
            continue
        if stripped == "architecture_requests:" and (not next_line or not next_line.startswith("    - ")):
            output.append("  architecture_requests: []")
            continue
        if stripped == "constraints:" and (not next_line or not next_line.startswith("    ")):
            output.append("  constraints: {}")
            continue
        if stripped == "tags:" and (not next_line or not next_line.startswith("    - ")):
            output.append("  tags: []")
            continue
        if stripped == "recent_updates:" and (not next_line or not next_line.startswith("    - ")):
            output.append("  recent_updates: []")
            continue

        output.append(line)

    return "\n".join(output) + "\n"


def _load_profile_yaml(profile_path: str) -> dict[str, Any]:
    from runtime.profile_io import load_profile
    return load_profile(profile_path)


def _ensure_profile_baseline(profile_data: dict[str, Any]) -> None:
    profile_data.setdefault("name", "omg-project")
    profile_data.setdefault("description", "initialized by OMG standalone compat bootstrap")
    profile_data.setdefault("language", "unknown")
    profile_data.setdefault("framework", "unknown")
    profile_data.setdefault("stack", [])
    profile_data.setdefault("conventions", {})
    profile_data.setdefault("ai_behavior", {})


def _normalize_preferences_block(raw: Any) -> dict[str, Any]:
    block = raw if isinstance(raw, dict) else {}

    requests_obj = block.get("architecture_requests")
    architecture_requests: list[str] = []
    if isinstance(requests_obj, list):
        for value in requests_obj:
            text = str(value).strip()
            if text:
                architecture_requests.append(text)
            if len(architecture_requests) >= _PROFILE_ARCH_REQUEST_MAX:
                break

    constraints_obj = block.get("constraints")
    constraints: dict[str, Any] = {}
    if isinstance(constraints_obj, dict):
        for key, value in constraints_obj.items():
            normalized_key = _normalize_constraint_key(str(key))
            normalized_value = _normalize_constraint_value(value)
            if normalized_key and normalized_value is not None:
                constraints[normalized_key] = normalized_value

    routing_obj = block.get("routing")
    routing_map = routing_obj if isinstance(routing_obj, dict) else {}
    routing = {
        "prefer_clarification": bool(routing_map.get("prefer_clarification", False)),
    }

    return {
        "architecture_requests": architecture_requests,
        "constraints": constraints,
        "routing": routing,
    }


def _normalize_constraint_key(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]+", "", normalized)
    return normalized


def _normalize_constraint_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text else None


def _normalize_user_vector_block(raw: Any) -> dict[str, Any]:
    block = raw if isinstance(raw, dict) else {}

    tags_obj = block.get("tags")
    tags: list[str] = []
    if isinstance(tags_obj, list):
        for value in tags_obj:
            token = _normalize_tag_token(str(value))
            if token:
                tags.append(token)
            if len(tags) >= _PROFILE_TAG_MAX:
                break

    summary = ""
    summary_obj = block.get("summary")
    if isinstance(summary_obj, str):
        summary = " ".join(summary_obj.strip().split())[:_PROFILE_SUMMARY_MAX_CHARS]

    confidence = 0.0
    confidence_obj = block.get("confidence")
    if isinstance(confidence_obj, (int, float, str)):
        try:
            confidence = float(confidence_obj)
        except (TypeError, ValueError):
            confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "tags": tags,
        "summary": summary,
        "confidence": confidence,
    }


def _normalize_tag_token(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_\-]+", "", normalized)
    return normalized


def _normalize_provenance_block(raw: Any) -> dict[str, Any]:
    block = raw if isinstance(raw, dict) else {}
    updates_obj = block.get("recent_updates")
    updates: list[dict[str, str]] = []
    if isinstance(updates_obj, list):
        for entry in updates_obj:
            if not isinstance(entry, dict):
                continue
            run_id = str(entry.get("run_id", "")).strip()
            source = str(entry.get("source", "")).strip()
            field = str(entry.get("field", "")).strip()
            updated_at = str(entry.get("updated_at", "")).strip()
            if not (run_id and source and field and updated_at):
                continue
            updates.append(
                {
                    "run_id": run_id,
                    "source": source,
                    "field": field,
                    "updated_at": updated_at,
                }
            )
            if len(updates) >= _PROFILE_RECENT_UPDATES_MAX:
                break
    return {"recent_updates": updates}


def _write_project_settings_preset(project_dir: str, preset: str) -> None:
    """Persist preset metadata into project settings when settings.json exists."""
    settings_path = os.path.join(project_dir, "settings.json")
    if not os.path.exists(settings_path):
        return

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return

    if not isinstance(settings, dict):
        return

    omg = settings.get("_omg")
    if not isinstance(omg, dict):
        omg = {}
    features = omg.get("features")
    if not isinstance(features, dict):
        features = {}

    features.update(get_preset_features(preset))
    omg["features"] = features
    omg["preset"] = preset
    omg["_version"] = CANONICAL_VERSION
    settings["_omg"] = omg

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=True)
        f.write("\n")


def run_setup_wizard(
    project_dir: str,
    non_interactive: bool = False,
    *,
    mode: str | None = None,
    setup_mode: str | None = None,
    adopt: str = "auto",
    preset: str | None = None,
    selected_mcps: list[str] | None = None,
    browser_enabled: bool = False,
) -> dict[str, Any]:
    """Run the OMG setup wizard.

    Args:
        project_dir: Path to the project directory.
        non_interactive: If True, skip prompts and use defaults (for CI).
        mode: Optional adoption mode override (`omg-only` or `coexist`).
        adopt: Adoption detection mode (currently only `auto` is meaningful).
        preset: Optional preset override.

    Returns:
        Dict with wizard results including status and step outcomes.
        If feature is disabled, returns {"status": "disabled", "message": "..."}.
    """
    if not is_setup_enabled():
        return {
            "status": "disabled",
            "message": "Setup wizard disabled. Set OMG_SETUP_ENABLED=1 to enable.",
        }

    selected_preset = resolve_preset(preset or ("balanced" if non_interactive else "safe"))
    selected_setup_mode = select_setup_mode(setup_mode)
    adoption = build_adoption_report(
        project_dir,
        requested_mode=mode,
        preset=selected_preset,
        adopt=adopt,
    )

    clis = detect_clis()
    auth = check_auth()
    mcp = configure_mcp(project_dir, clis, preset=selected_preset, selected_ids=selected_mcps)
    prefs = set_preferences(
        project_dir,
        {
            "preset": selected_preset,
            "selected_mcps": selected_mcps,
            "browser_capability": {"enabled": browser_enabled},
        },
    )
    report_path = write_adoption_report(project_dir, adoption)
    adoption["report_path"] = report_path

    return {
        "status": "complete",
        "setup_mode": {
            "choices": get_mode_choices(),
            "selected": selected_setup_mode,
            "profile": get_mode_profile(selected_setup_mode),
        },
        "clis_detected": clis,
        "auth_status": auth,
        "mcp_configured": mcp,
        "preferences": prefs,
        "adoption": adoption,
    }
