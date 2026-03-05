"""OpenCode CLI provider -- implements CLIProvider for the ``opencode`` binary."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from typing import Any

from runtime.cli_provider import CLIProvider, register_provider
from runtime.tmux_session_manager import TmuxSessionManager

_logger = logging.getLogger(__name__)


class OpenCodeProvider(CLIProvider):
    """CLIProvider implementation for the OpenCode CLI (``opencode``)."""

    # -- identity -----------------------------------------------------------

    def get_name(self) -> str:  # noqa: D401
        """Return the canonical provider name."""
        return "opencode"

    # -- detection ----------------------------------------------------------

    def detect(self) -> bool:
        """Return ``True`` when the ``opencode`` binary is available on PATH."""
        return shutil.which("opencode") is not None

    # -- authentication -----------------------------------------------------

    def check_auth(self) -> tuple[bool | None, str]:
        """Check OpenCode authentication status via ``opencode auth list``."""
        try:
            result = self.run_tool(["opencode", "auth", "list"], timeout=30)
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip() or result.stdout.strip()
        except Exception as exc:
            return None, f"opencode auth check failed: {exc}"

    # -- invocation ---------------------------------------------------------

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``opencode run`` via subprocess."""
        try:
            result = self.run_tool(
                ["opencode", "run", prompt],
                timeout=timeout,
            )
            return {
                "model": "opencode-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "opencode-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "opencode-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_json(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``opencode run --format json`` for raw JSON event stream output."""
        try:
            result = self.run_tool(
                ["opencode", "run", "--format", "json", prompt],
                timeout=timeout,
            )
            return {
                "model": "opencode-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "opencode-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "opencode-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``opencode run`` via a persistent tmux session.

        Falls back to :meth:`invoke` on failure.
        """
        try:
            mgr = TmuxSessionManager()
            session_name = mgr.make_session_name("opencode", unique_id=str(uuid.uuid4())[:8])
            session = mgr.get_or_create_session(session_name)
            output = mgr.send_command(session, ["opencode", "run", prompt], timeout=timeout)
            mgr.kill_session(session)
            return {"model": "opencode-cli", "output": output, "exit_code": 0}
        except Exception as exc:
            _logger.warning("tmux opencode invocation failed, falling back to subprocess: %s", exc)
            return self.invoke(prompt, project_dir, timeout=timeout)

    # -- command helpers ----------------------------------------------------

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        """Return the non-interactive command for opencode."""
        return ["opencode", "run", prompt]

    # -- configuration ------------------------------------------------------

    def get_config_path(self) -> str:
        """Return the OpenCode configuration file path."""
        return os.path.expanduser("~/.config/opencode/opencode.json")

    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:
        """Write an MCP server entry to ``~/.config/opencode/opencode.json``.

        Uses JSON format with ``mcp`` key, ``type: "remote"``, and ``url`` field,
        merging into any existing configuration.
        """
        config_path = self.get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        # Load existing config or start fresh
        existing: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]
        if os.path.exists(config_path):
            with open(config_path) as fh:
                try:
                    existing = json.load(fh)
                except (json.JSONDecodeError, ValueError):
                    existing = {}

        # Ensure mcp dict exists
        if "mcp" not in existing:
            existing["mcp"] = {}

        existing["mcp"][server_name] = {"type": "remote", "url": server_url}

        with open(config_path, "w") as fh:
            json.dump(existing, fh, indent=2)


# -- auto-register on import -----------------------------------------------
register_provider(OpenCodeProvider())
