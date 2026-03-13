"""CLI provider abstractions and provider registry."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any
from typing import Mapping


def _run_tool(
    cmd: list[str],
    *,
    timeout: int = 30,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external tool with a mandatory timeout."""
    proc_env = os.environ.copy()
    if env:
        proc_env.update({key: str(value) for key, value in env.items()})
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=cwd,
        env=proc_env,
    )


class CLIProvider(ABC):
    """Abstract contract for external CLI providers."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the provider name (for example: codex or gemini)."""

    @abstractmethod
    def detect(self) -> bool:
        """Return True when the provider CLI binary is available on PATH."""

    @abstractmethod
    def check_auth(self) -> tuple[bool | None, str]:
        """Return provider authentication state and a human-readable message."""

    @abstractmethod
    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke provider directly using subprocess mode."""

    @abstractmethod
    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Invoke provider through tmux-managed execution mode."""

    @abstractmethod
    def get_non_interactive_cmd(self, prompt: str) -> list[str]:
        """Return non-interactive command arguments for the provider CLI."""

    @abstractmethod
    def get_config_path(self) -> str:
        """Return provider configuration file path."""

    @abstractmethod
    def write_mcp_config(self, server_url: str, server_name: str = "memory-server") -> None:
        """Write or update MCP server configuration for this provider."""

    def run_tool(
        self,
        cmd: list[str],
        *,
        timeout: int = 30,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute subprocess commands via mandatory timeout helper."""
        return _run_tool(cmd, timeout=timeout, cwd=cwd, env=env)


_PROVIDER_REGISTRY: dict[str, CLIProvider] = {}


def register_provider(provider: CLIProvider) -> None:
    """Register a CLI provider by its canonical name."""
    _PROVIDER_REGISTRY[provider.get_name()] = provider


def get_provider(name: str) -> CLIProvider | None:
    """Return a registered CLI provider by name."""
    return _PROVIDER_REGISTRY.get(name)


def list_available_providers() -> list[str]:
    """Return registered provider names in insertion order."""
    return list(_PROVIDER_REGISTRY)


__all__ = [
    "CLIProvider",
    "_PROVIDER_REGISTRY",
    "get_provider",
    "list_available_providers",
    "register_provider",
]
