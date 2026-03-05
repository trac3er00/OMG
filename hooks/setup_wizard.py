"""OMG Setup Wizard — interactive CLI detection, auth verification, and MCP configuration.

Feature-gated: requires OMG_SETUP_ENABLED=1 (default off).
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, cast

import yaml

from _common import get_feature_flag

# Ensure project root is on sys.path for runtime imports
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from runtime.cli_provider import get_provider, list_available_providers  # noqa: E402
from runtime.mcp_config_writers import (  # noqa: E402
    write_claude_mcp_config,
    write_codex_mcp_config,
    write_gemini_mcp_config,
    write_opencode_mcp_config,
    write_kimi_mcp_config,
)

# Trigger provider auto-registration on import
import runtime.providers.codex_provider  # noqa: E402, F401
import runtime.providers.gemini_provider  # noqa: E402, F401
import runtime.providers.opencode_provider  # noqa: E402, F401
import runtime.providers.kimi_provider  # noqa: E402, F401

_logger = logging.getLogger(__name__)

_INSTALL_HINTS: dict[str, str] = {
    "codex": "npm install -g @openai/codex",
    "gemini": "npm install -g @google/gemini-cli",
    "opencode": "npm install -g opencode-ai  (or: curl -fsSL https://opencode.ai/install | bash)",
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

MCP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "context7",
        "name": "Context7",
        "description": "Upstash Context7 MCP server for context management",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "default": True,
        "category": "productivity",
    },
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "ModelContextProtocol filesystem server for file operations",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.expanduser("~")],
        "default": True,
        "category": "system",
    },
    {
        "id": "websearch",
        "name": "Web Search",
        "description": "Web search MCP server for internet queries",
        "command": "npx",
        "args": ["-y", "@zhafron/mcp-web-search"],
        "default": True,
        "category": "search",
    },
    {
        "id": "chrome-devtools",
        "name": "Chrome DevTools",
        "description": "Chrome DevTools MCP server for browser automation",
        "command": "npx",
        "args": ["-y", "chrome-devtools-mcp@latest"],
        "default": True,
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
        "default": True,
        "category": "memory",
    },
    {
        "id": "github",
        "name": "GitHub",
        "description": "ModelContextProtocol GitHub server for repository operations",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "default": False,
        "category": "vcs",
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer",
        "description": "ModelContextProtocol Puppeteer server for browser automation",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "default": False,
        "category": "browser",
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "ModelContextProtocol Brave Search server",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "default": False,
        "category": "search",
    },
    {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "description": "ModelContextProtocol Sequential Thinking server for reasoning",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "default": False,
        "category": "reasoning",
    },
    {
        "id": "grep-app",
        "name": "Grep App",
        "description": "Grep App MCP server for code search",
        "command": "npx",
        "args": ["-y", "grep-app-mcp"],
        "default": False,
        "category": "search",
    },
    {
        "id": "memory-graph",
        "name": "Memory Graph",
        "description": "ModelContextProtocol Memory server for knowledge graphs",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "default": False,
        "category": "memory",
    },
]


def get_mcp_catalog() -> list[dict[str, Any]]:
    """Return the MCP catalog.

    Returns:
        List of MCP server definitions with id, name, description, command, args, default, and category.
    """
    return MCP_CATALOG


def build_mcp_config(selected_ids: list[str]) -> dict[str, Any]:
    """Build .mcp.json configuration from selected MCP server IDs.

    Args:
        selected_ids: List of MCP server IDs to include in the config.

    Returns:
        Dict with 'mcpServers' key containing the MCP server configurations.
    """
    mcp_servers: dict[str, Any] = {}

    for mcp in MCP_CATALOG:
        if mcp["id"] not in selected_ids:
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


def select_mcps(selected_ids: list[str] | None = None) -> dict[str, Any]:
    """Build MCP config from selected IDs.

    Args:
        selected_ids: List of MCP IDs to include. If None, uses defaults.

    Returns:
        dict with mcpServers key (ready to write as .mcp.json)
    """
    if selected_ids is None:
        selected_ids = [m["id"] for m in MCP_CATALOG if m["default"]]
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
        provider: CLI provider name (e.g. "codex", "gemini", "kimi", "opencode").

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
        "opencode": {
            "install": "npm install -g opencode-ai",
            "auth": "opencode auth login",
            "verify": "opencode --version",
            "subscription": "Requires Anthropic API key or Claude subscription",
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


def configure_mcp(
    project_dir: str,
    detected_clis: dict[str, Any],
    server_url: str = "http://127.0.0.1:8765/mcp",
    server_name: str = "omg-memory",
) -> dict[str, Any]:
    """Configure MCP memory server for authenticated CLIs.

    For each CLI in detected_clis where detected_clis[cli]["detected"] == True,
    calls the appropriate writer from runtime.mcp_config_writers.

    Args:
        project_dir: Path to the project directory.
        detected_clis: Dict of CLI detection results from detect_clis().
        server_url: MCP server URL (default: http://127.0.0.1:8765/mcp).
        server_name: MCP server name (default: omg-memory).

    Returns:
        Dict with keys:
        - status: "ok" on success
        - configured: List of CLI names that were successfully configured
        - errors: Dict of CLI name → error message for failures
    """
    configured: list[str] = []
    errors: dict[str, str] = {}

    # Always write Claude config
    try:
        write_claude_mcp_config(project_dir, server_url, server_name)
    except Exception as exc:
        _logger.warning("Failed to write Claude MCP config: %s", exc)
        errors["claude"] = str(exc)

    # Write configs for detected CLIs
    cli_writers = {
        "codex": write_codex_mcp_config,
        "gemini": write_gemini_mcp_config,
        "opencode": write_opencode_mcp_config,
        "kimi": write_kimi_mcp_config,
    }

    for cli_name, writer_func in cli_writers.items():
        cli_info = detected_clis.get(cli_name, {})
        if not cli_info.get("detected", False):
            continue

        try:
            writer_func(server_url, server_name)
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
        "opencode": {"subscription": "free", "max_parallel_agents": 1},
        "kimi": {"subscription": "free", "max_parallel_agents": 1},
    }
    default_config: dict[str, Any] = {
        "version": "2.0",
        "cli_configs": default_cli_configs,
    }

    # Merge custom preferences if provided
    if preferences and isinstance(preferences, dict):
        cli_configs = preferences.get("cli_configs")
        if isinstance(cli_configs, dict):
            default_cli_configs.update(cast(dict[str, Any], cli_configs))

    # Create .omg/state directory if needed
    state_dir = os.path.join(project_dir, ".omg", "state")
    os.makedirs(state_dir, exist_ok=True)

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


def run_setup_wizard(project_dir: str, non_interactive: bool = False) -> dict[str, Any]:
    """Run the OMG setup wizard.

    Args:
        project_dir: Path to the project directory.
        non_interactive: If True, skip prompts and use defaults (for CI).

    Returns:
        Dict with wizard results including status and step outcomes.
        If feature is disabled, returns {"status": "disabled", "message": "..."}.
    """
    if not is_setup_enabled():
        return {
            "status": "disabled",
            "message": "Setup wizard disabled. Set OMG_SETUP_ENABLED=1 to enable.",
        }

    # Run each wizard step (stubs for now — T15/T16/T17 fill these in)
    clis = detect_clis()
    auth = check_auth()
    mcp = configure_mcp(project_dir, clis)
    prefs = set_preferences(project_dir, {})

    return {
        "status": "complete",
        "clis_detected": clis,
        "auth_status": auth,
        "mcp_configured": mcp,
        "preferences": prefs,
    }
