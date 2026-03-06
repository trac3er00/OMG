"""Tests for the registered Codex CLI provider."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import runtime.providers.codex_provider  # noqa: F401

from runtime.cli_provider import ContractCLIProvider, get_provider


def _provider() -> ContractCLIProvider:
    provider = get_provider("codex")
    assert provider is not None
    assert isinstance(provider, ContractCLIProvider)
    return provider


def test_codex_provider_is_registered():
    provider = _provider()
    assert provider.get_name() == "codex"


def test_codex_provider_detects_binary():
    provider = _provider()

    with patch("shutil.which", return_value="/usr/local/bin/codex"):
        assert provider.detect() is True

    with patch("shutil.which", return_value=None):
        assert provider.detect() is False


def test_codex_provider_reports_auth_probe_as_unsupported():
    provider = _provider()
    assert provider.check_auth() == (None, "auth status check not supported")


def test_codex_provider_invokes_current_non_interactive_command():
    provider = _provider()
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"ok":true}', stderr="")

    with patch.object(provider, "detect", return_value=True), patch(
        "runtime.cli_provider.subprocess.run",
        return_value=fake,
    ) as run:
        result = provider.invoke("fix bug", "/tmp/project", timeout=60)

    run.assert_called_once_with(
        ["codex", "exec", "--json", "fix bug"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result["model"] == "codex-cli"
    assert result["exit_code"] == 0


def test_codex_provider_non_interactive_command_and_config_path():
    provider = _provider()
    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "codex",
        "exec",
        "--json",
        "Reply with OK.",
    ]
    assert provider.get_config_path().endswith(".codex/config.toml")
