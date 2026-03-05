"""Codex CLI provider — implements CLIProvider for the ``codex`` binary."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from typing import Any

from runtime.cli_provider import CLIProvider, register_provider
from runtime.tmux_session_manager import TmuxSessionManager

_logger = logging.getLogger(__name__)


class CodexProvider(CLIProvider):
    """CLIProvider implementation for the Codex CLI (``codex``)."""

    # -- identity -----------------------------------------------------------

    def get_name(self) -> str:  # noqa: D401
        """Return the canonical provider name."""
        return "codex"

    # -- detection ----------------------------------------------------------

    def detect(self) -> bool:
        """Return ``True`` when the ``codex`` binary is available on PATH."""
        return shutil.which("codex") is not None

    # -- authentication -----------------------------------------------------

    def check_auth(self) -> tuple[bool | None, str]:
        """Check Codex authentication status via ``codex auth status``."""
        try:
            result = self.run_tool(["codex", "auth", "status"], timeout=30)
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip() or result.stdout.strip()
        except Exception as exc:
            return None, f"codex auth check failed: {exc}"

    # -- invocation ---------------------------------------------------------

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``codex exec --json`` via subprocess."""
        try:
            result = self.run_tool(
                ["codex", "exec", "--json", prompt],
                timeout=timeout,
            )
            return {
                "model": "codex-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "codex-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "codex-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``codex exec --json`` via a persistent tmux session.

        Falls back to :meth:`invoke` on failure.
        """
        try:
            mgr = TmuxSessionManager()
            session_name = mgr.make_session_name("codex", unique_id=str(uuid.uuid4())[:8])
            session = mgr.get_or_create_session(session_name)
            output = mgr.send_command(session, f"codex exec --json '{prompt}'", timeout=timeout)
            mgr.kill_session(session)
            return {"model": "codex-cli", "output": output, "exit_code": 0}
        except Exception as exc:
            _logger.warning("tmux codex invocation failed, falling back to subprocess: %s", exc)
            return self.invoke(prompt, project_dir, timeout=timeout)

    # -- command helpers ----------------------------------------------------

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        """Return the non-interactive command for codex."""
        return ["codex", "exec", "--json", prompt]

    # -- configuration ------------------------------------------------------

    def get_config_path(self) -> str:
        """Return the Codex configuration file path."""
        return os.path.expanduser("~/.codex/config.toml")

    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:
        """Write an MCP server entry to ``~/.codex/config.toml``."""
        config_path = self.get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        entry = (
            f'[mcp_servers."{server_name}"]\n'
            f'url = "{server_url}"\n'
        )

        # Append or create
        mode = "a" if os.path.exists(config_path) else "w"
        with open(config_path, mode) as fh:
            fh.write(entry)


# -- auto-register on import -----------------------------------------------
register_provider(CodexProvider())
