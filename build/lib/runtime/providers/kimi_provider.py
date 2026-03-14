"""Kimi Code CLI provider -- implements CLIProvider for the ``kimi`` binary."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import uuid
from typing import Any

from runtime.cli_provider import CLIProvider, register_provider
from runtime.host_parity import normalize_output
from runtime.mcp_config_writers import write_kimi_mcp_config
from runtime.tmux_session_manager import TmuxSessionManager

_logger = logging.getLogger(__name__)


def _attach_normalized_output(payload: dict[str, Any], *, prompt: str, project_dir: str) -> dict[str, Any]:
    normalized = normalize_output(
        "kimi",
        payload,
        context={"prompt": prompt, "project_dir": project_dir},
    )
    merged = dict(payload)
    merged["normalized_output"] = normalized
    return merged

HOST_RULES = {
    "compilation_targets": [".kimi/mcp.json"],
    "mcp": ["omg-control"],
    "skills": ["omg/control-plane", "omg/mcp-fabric"],
    "automations": ["contract-validate", "provider-routing"],
}


class KimiCodeProvider(CLIProvider):
    """CLIProvider implementation for the Kimi Code CLI (``kimi``)."""

    # -- identity -----------------------------------------------------------

    def get_name(self) -> str:  # noqa: D401
        """Return the canonical provider name."""
        return "kimi"

    # -- detection ----------------------------------------------------------

    def detect(self) -> bool:
        """Return ``True`` when the ``kimi`` binary is available on PATH."""
        return shutil.which("kimi") is not None

    # -- authentication -----------------------------------------------------

    def check_auth(self) -> tuple[bool | None, str]:
        """Check Kimi authentication by parsing ``~/.kimi/config.toml`` for stored credentials."""
        try:
            config_path = os.path.expanduser("~/.kimi/config.toml")
            if not os.path.exists(config_path):
                return False, "not authenticated — config file not found"

            with open(config_path) as fh:
                content = fh.read()

            # Look for a token entry in the TOML file
            if "token" in content:
                return True, "authenticated"
            return False, "not authenticated — no token in config"
        except Exception as exc:
            return None, f"kimi auth check failed: {exc}"

    # -- invocation ---------------------------------------------------------

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``kimi --print -p`` via subprocess."""
        try:
            result = self.run_tool(
                ["kimi", "--print", "-p", prompt],
                timeout=timeout,
                cwd=project_dir,
                env={"CLAUDE_PROJECT_DIR": project_dir},
            )
            return _attach_normalized_output({
                "model": "kimi-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }, prompt=prompt, project_dir=project_dir)
        except subprocess.TimeoutExpired:
            return {"error": "kimi-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "kimi-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_json(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``kimi --print --output-format stream-json -p`` for JSONL event stream output."""
        try:
            result = self.run_tool(
                ["kimi", "--print", "--output-format", "stream-json", "-p", prompt],
                timeout=timeout,
                cwd=project_dir,
                env={"CLAUDE_PROJECT_DIR": project_dir},
            )
            return _attach_normalized_output({
                "model": "kimi-cli",
                "output": result.stdout,
                "exit_code": result.returncode,
            }, prompt=prompt, project_dir=project_dir)
        except subprocess.TimeoutExpired:
            return {"error": "kimi-cli timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": "kimi-cli not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke ``kimi --print -p`` via a persistent tmux session.

        Falls back to :meth:`invoke` on failure.
        """
        try:
            mgr = TmuxSessionManager()
            session_name = mgr.make_session_name("kimi", unique_id=str(uuid.uuid4())[:8])
            session = mgr.get_or_create_session(session_name, cwd=project_dir)
            output = mgr.send_command(
                session,
                (
                    f"env CLAUDE_PROJECT_DIR={shlex.quote(project_dir)} "
                    f"kimi --print -p {shlex.quote(prompt)}"
                ),
                timeout=timeout,
            )
            mgr.kill_session(session)
            return _attach_normalized_output(
                {"model": "kimi-cli", "output": output, "exit_code": 0},
                prompt=prompt,
                project_dir=project_dir,
            )
        except Exception as exc:
            _logger.warning("tmux kimi invocation failed, falling back to subprocess: %s", exc)
            return self.invoke(prompt, project_dir, timeout=timeout)

    # -- command helpers ----------------------------------------------------

    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        """Return the non-interactive command for kimi."""
        return ["kimi", "--print", "-p", prompt]

    # -- configuration ------------------------------------------------------

    def get_config_path(self) -> str:
        """Return the Kimi MCP configuration file path."""
        return os.path.expanduser("~/.kimi/mcp.json")

    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:
        """Write an MCP server entry to ``~/.kimi/mcp.json``.

        Uses standard ``mcpServers`` JSON format with ``type: "http"`` and ``url`` field,
        merging into any existing configuration.
        """
        write_kimi_mcp_config(server_url, server_name, config_path=self.get_config_path())


# -- auto-register on import -----------------------------------------------
register_provider(KimiCodeProvider())
