"""Tests for the registered OpenCode CLI provider."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import runtime.providers.opencode_provider  # noqa: F401

from runtime.cli_provider import ContractCLIProvider, get_provider


def _provider() -> ContractCLIProvider:
    provider = get_provider("opencode")
    assert provider is not None
    assert isinstance(provider, ContractCLIProvider)
    return provider


def test_opencode_provider_is_registered():
    provider = _provider()
    assert provider.get_name() == "opencode"


def test_opencode_provider_detects_binary():
    provider = _provider()

    with patch("shutil.which", return_value="/usr/local/bin/opencode"):
        assert provider.detect() is True

    with patch("shutil.which", return_value=None):
        assert provider.detect() is False


def test_opencode_provider_reports_auth_probe_success():
    provider = _provider()
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="authenticated\n", stderr="")

    with patch("runtime.cli_provider.subprocess.run", return_value=fake) as run:
        result = provider.check_auth()

    run.assert_called_once_with(
        ["opencode", "auth", "list"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result == (True, "authenticated")


def test_opencode_provider_reports_auth_probe_failure():
    provider = _provider()
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not authenticated")

    with patch("runtime.cli_provider.subprocess.run", return_value=fake):
        ok, msg = provider.check_auth()

    assert ok is False
    assert "not authenticated" in msg


def test_opencode_provider_invokes_current_non_interactive_command():
    provider = _provider()
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"ok":true}', stderr="")

    with patch.object(provider, "detect", return_value=True), patch(
        "runtime.cli_provider.subprocess.run",
        return_value=fake,
    ) as run:
        result = provider.invoke("fix bug", "/tmp/project", timeout=60)

    run.assert_called_once_with(
        ["opencode", "run", "fix bug", "--format", "json", "--dir", "/tmp/project"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result["model"] == "opencode-cli"
    assert result["exit_code"] == 0


def test_opencode_provider_non_interactive_command_and_config_path():
    provider = _provider()
    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "opencode",
        "run",
        "Reply with OK.",
        "--format",
        "json",
        "--dir",
        "/tmp/project",
    ]
    assert provider.get_config_path().endswith(".config/opencode/opencode.json")
