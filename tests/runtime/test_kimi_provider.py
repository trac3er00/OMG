"""Tests for the registered Kimi CLI provider."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import runtime.providers.kimi_provider  # noqa: F401

from runtime.cli_provider import ContractCLIProvider, get_provider


def _provider() -> ContractCLIProvider:
    provider = get_provider("kimi")
    assert provider is not None
    assert isinstance(provider, ContractCLIProvider)
    return provider


def test_kimi_provider_is_registered():
    provider = _provider()
    assert provider.get_name() == "kimi"


def test_kimi_provider_detects_binary():
    provider = _provider()

    with patch("shutil.which", return_value="/usr/local/bin/kimi"):
        assert provider.detect() is True

    with patch("shutil.which", return_value=None):
        assert provider.detect() is False


def test_kimi_provider_reports_auth_probe_as_unsupported():
    provider = _provider()
    assert provider.check_auth() == (None, "auth status check not supported")


def test_kimi_provider_invokes_current_non_interactive_command():
    provider = _provider()
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="done", stderr="")

    with patch.object(provider, "detect", return_value=True), patch(
        "runtime.cli_provider.subprocess.run",
        return_value=fake,
    ) as run:
        result = provider.invoke("inspect runtime", "/tmp/project", timeout=30)

    run.assert_called_once_with(
        [
            "kimi",
            "--print",
            "--output-format",
            "text",
            "--final-message-only",
            "-w",
            "/tmp/project",
            "-p",
            "inspect runtime",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result["model"] == "kimi-cli"
    assert result["exit_code"] == 0


def test_kimi_provider_non_interactive_command_and_config_path():
    provider = _provider()
    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "kimi",
        "--print",
        "--output-format",
        "text",
        "--final-message-only",
        "-w",
        "/tmp/project",
        "-p",
        "Reply with OK.",
    ]
    assert provider.get_config_path().endswith(".kimi/config.toml")
