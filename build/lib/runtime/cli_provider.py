"""CLI provider contracts and registry for OMG runtime."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess
from typing import Any


_CLI_CONTRACTS: dict[str, dict[str, Any]] = {
    "codex": {
        "binary": "codex",
        "auth_probe_kind": "none",
        "auth_probe": None,
        "non_interactive_builder": lambda prompt, _project_dir: ["codex", "exec", "--json", prompt],
    },
    "gemini": {
        "binary": "gemini",
        "auth_probe_kind": "none",
        "auth_probe": None,
        "non_interactive_builder": lambda prompt, _project_dir: ["gemini", "-p", prompt, "--output-format", "json"],
    },
    "kimi": {
        "binary": "kimi",
        "auth_probe_kind": "none",
        "auth_probe": None,
        "non_interactive_builder": lambda prompt, project_dir: [
            "kimi",
            "--print",
            "--output-format",
            "text",
            "--final-message-only",
            "-w",
            project_dir,
            "-p",
            prompt,
        ],
    },
}


def _run_tool(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def get_cli_contract(tool_name: str) -> dict[str, Any] | None:
    """Return a copy of the known CLI contract for a provider."""
    contract = _CLI_CONTRACTS.get(tool_name)
    return dict(contract) if contract is not None else None


def build_non_interactive_command(tool_name: str, prompt: str, project_dir: str) -> list[str] | None:
    """Build the current non-interactive command for a provider."""
    contract = _CLI_CONTRACTS.get(tool_name)
    if contract is None:
        return None

    builder = contract.get("non_interactive_builder")
    if not callable(builder):
        return None
    return list(builder(prompt, project_dir))


class CLIProvider(ABC):
    """Abstract provider interface for external CLI-backed models."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the provider name."""

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the provider binary is available."""

    @abstractmethod
    def check_auth(self) -> tuple[bool | None, str]:
        """Return auth state and explanatory message."""

    @abstractmethod
    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
        """Invoke the provider non-interactively."""

    @abstractmethod
    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
        """Invoke the provider via tmux or fallback."""

    @abstractmethod
    def get_non_interactive_cmd(self, prompt: str, project_dir: str) -> list[str]:
        """Return the provider's non-interactive command."""

    @abstractmethod
    def get_config_path(self) -> str:
        """Return the provider's primary config path."""


class ContractCLIProvider(CLIProvider):
    """Contract-backed provider implementation for current OMG Phase 1."""

    def __init__(self, name: str, *, config_path: str, model_name: str) -> None:
        self._name = name
        self._config_path = config_path
        self._model_name = model_name

    def get_name(self) -> str:
        return self._name

    def detect(self) -> bool:
        contract = _CLI_CONTRACTS.get(self._name)
        if contract is None:
            return False
        binary = str(contract.get("binary", ""))
        return bool(binary and shutil.which(binary) is not None)

    def check_auth(self) -> tuple[bool | None, str]:
        contract = _CLI_CONTRACTS.get(self._name)
        if contract is None:
            return None, "provider contract missing"

        probe_kind = contract.get("auth_probe_kind")
        probe_cmd = contract.get("auth_probe")

        if probe_kind == "list" and isinstance(probe_cmd, list):
            try:
                result = _run_tool([str(part) for part in probe_cmd], timeout=15)
            except subprocess.TimeoutExpired:
                return None, "auth probe timed out"
            except FileNotFoundError:
                return False, "CLI is not installed"
            except Exception as exc:
                return None, f"auth probe failed: {exc}"

            output = f"{result.stdout}\n{result.stderr}".strip()
            if result.returncode == 0:
                return True, output or "auth probe succeeded"
            return False, output or f"auth probe failed (exit={result.returncode})"

        return None, "auth status check not supported"

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
        if not self.detect():
            return {"error": f"{self._model_name} not found", "fallback": "claude"}

        cmd = self.get_non_interactive_cmd(prompt, project_dir)
        try:
            result = _run_tool(cmd, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"error": f"{self._model_name} timeout", "fallback": "claude"}
        except FileNotFoundError:
            return {"error": f"{self._model_name} not found", "fallback": "claude"}
        except Exception as exc:
            return {"error": str(exc), "fallback": "claude"}

        return {
            "model": self._model_name,
            "output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
        # Task 3 only promotes the common contract. tmux specialization follows later.
        return self.invoke(prompt, project_dir, timeout=timeout)

    def get_non_interactive_cmd(self, prompt: str, project_dir: str) -> list[str]:
        cmd = build_non_interactive_command(self._name, prompt, project_dir)
        if cmd is None:
            raise ValueError(f"missing contract builder for {self._name}")
        return cmd

    def get_config_path(self) -> str:
        return self._config_path


_PROVIDER_REGISTRY: dict[str, CLIProvider] = {}


def register_provider(provider: CLIProvider) -> None:
    """Register a provider instance by its canonical name."""
    _PROVIDER_REGISTRY[provider.get_name()] = provider


def get_provider(name: str) -> CLIProvider | None:
    """Look up a provider by name."""
    return _PROVIDER_REGISTRY.get(name)


def list_available_providers() -> list[str]:
    """Return provider names in registration order."""
    return list(_PROVIDER_REGISTRY)


def default_config_path(provider_name: str) -> str:
    """Return the default config path for a known provider."""
    defaults = {
        "codex": str(Path.home() / ".codex" / "config.toml"),
        "gemini": str(Path.home() / ".gemini" / "settings.json"),
        "kimi": str(Path.home() / ".kimi" / "config.toml"),
    }
    return defaults.get(provider_name, "")


__all__ = [
    "CLIProvider",
    "ContractCLIProvider",
    "build_non_interactive_command",
    "default_config_path",
    "get_cli_contract",
    "get_provider",
    "list_available_providers",
    "register_provider",
]
