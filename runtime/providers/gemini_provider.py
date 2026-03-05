"""Gemini CLI provider — implements CLIProvider for the ``gemini`` binary."""

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


class GeminiProvider(CLIProvider):
    """CLIProvider implementation for the Gemini CLI (``gemini``)."""

    # -- identity -----------------------------------------------------------

    def get_name(self) -> str:  # noqa: D401
        """Return the canonical provider name."""
        return "gemini"

    # -- detection ----------------------------------------------------------

    def detect(self) -> bool:
        """Return ``True`` when the ``gemini`` binary is available on PATH."""
        return shutil.which("gemini") is not None

    # -- authentication -----------------------------------------------------

    def check_auth(self) -> tuple[bool | None, str]:
        """Check Gemini authentication status via ``gemini auth status``."""
        try:
            result = self.run_tool(["gemini", "auth", "status"], timeout=30)
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip() or result.stdout.strip()
        except Exception as exc:
            return None, f"gemini auth check failed: {exc}"

    # -- invocation ---------------------------------------------------------

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``gemini -p`` via subprocess.

        Gemini CLI has no ``--json`` flag — output is plain text stdout.
        """
        try:
            result = self.run_tool(
                ["gemini", "-p", prompt],
                timeout=timeout,
            )
            return {
                "model": "gemini-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "gemini-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "gemini-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``gemini -p`` via a persistent tmux session.

        Falls back to :meth:`invoke` on failure.
        """
        try:
            mgr = TmuxSessionManager()
            session_name = mgr.make_session_name("gemini", unique_id=str(uuid.uuid4())[:8])
            session = mgr.get_or_create_session(session_name)
            output = mgr.send_command(session, ["gemini", "-p", prompt], timeout=timeout)
            mgr.kill_session(session)
            return {"model": "gemini-cli", "output": output, "exit_code": 0}
        except Exception as exc:
            _logger.warning("tmux gemini invocation failed, falling back to subprocess: %s", exc)
            return self.invoke(prompt, project_dir, timeout=timeout)

    # -- command helpers ----------------------------------------------------

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        """Return the non-interactive command for gemini."""
        return ["gemini", "-p", prompt]

    # -- configuration ------------------------------------------------------

    def get_config_path(self) -> str:
        """Return the Gemini configuration file path."""
        return os.path.expanduser("~/.gemini/settings.json")

    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:
        """Write an MCP server entry to ``~/.gemini/settings.json``.

        Uses JSON format with ``mcpServers`` key and ``httpUrl`` field,
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

        # Ensure mcpServers dict exists
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}

        existing["mcpServers"][server_name] = {"httpUrl": server_url}

        with open(config_path, "w") as fh:
            json.dump(existing, fh, indent=2)


# -- auto-register on import -----------------------------------------------
register_provider(GeminiProvider())
