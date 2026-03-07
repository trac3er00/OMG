"""Tests for GeminiProvider — the CLIProvider implementation for Gemini CLI."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from runtime.cli_provider import _PROVIDER_REGISTRY, get_provider
from runtime.providers.gemini_provider import GeminiProvider


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider() -> GeminiProvider:
    """Return a fresh GeminiProvider instance."""
    return GeminiProvider()


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

class TestGetName:
    def test_returns_gemini(self, provider: GeminiProvider) -> None:
        assert provider.get_name() == "gemini"


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

class TestDetect:
    @patch("shutil.which", return_value="/usr/local/bin/gemini")
    def test_returns_true_when_gemini_on_path(self, _which: MagicMock, provider: GeminiProvider) -> None:
        assert provider.detect() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_gemini_missing(self, _which: MagicMock, provider: GeminiProvider) -> None:
        assert provider.detect() is False


# ---------------------------------------------------------------------------
# check_auth
# ---------------------------------------------------------------------------

class TestCheckAuth:
    def test_returns_true_on_zero_exit(self, provider: GeminiProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="authenticated\n", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            ok, msg = provider.check_auth()
            mock_rt.assert_called_once_with(["gemini", "auth", "status"], timeout=30)
            assert ok is True
            assert "authenticated" in msg

    def test_returns_false_on_nonzero_exit(self, provider: GeminiProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not logged in")
        with patch.object(provider, "run_tool", return_value=fake):
            ok, msg = provider.check_auth()
            assert ok is False

    def test_returns_none_on_exception(self, provider: GeminiProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("gemini")):
            ok, msg = provider.check_auth()
            assert ok is None
            assert msg  # non-empty message


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------

class TestInvoke:
    def test_success_returns_model_output_exit(self, provider: GeminiProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="some output text", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke("fix bug", "/project", timeout=60)
            mock_rt.assert_called_once_with(["gemini", "-p", "fix bug"], timeout=60)
            assert result == {"model": "gemini-cli", "output": "some output text", "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: GeminiProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="gemini", timeout=120)):
            result = provider.invoke("slow task", "/project")
            assert result["error"] == "gemini-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: GeminiProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("gemini")):
            result = provider.invoke("task", "/project")
            assert result["error"] == "gemini-cli not found"
            assert result["fallback"] == "claude"

    def test_generic_exception_returns_error_fallback(self, provider: GeminiProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=OSError("broken pipe")):
            result = provider.invoke("task", "/project")
            assert "broken pipe" in result["error"]
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_tmux
# ---------------------------------------------------------------------------

class TestInvokeTmux:
    @patch("runtime.providers.gemini_provider.TmuxSessionManager")
    def test_success_returns_output(self, mock_mgr_cls: MagicMock, provider: GeminiProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-gemini-abc"
        mgr.get_or_create_session.return_value = "omg-gemini-abc"
        mgr.send_command.return_value = "gemini output here"
        mgr.kill_session.return_value = True

        result = provider.invoke_tmux("fix bug", "/project", timeout=90)

        mgr.make_session_name.assert_called_once()
        mgr.get_or_create_session.assert_called_once_with("omg-gemini-abc")
        mgr.send_command.assert_called_once()
        mgr.kill_session.assert_called_once_with("omg-gemini-abc")
        assert result == {"model": "gemini-cli", "output": "gemini output here", "exit_code": 0}

    @patch("runtime.providers.gemini_provider.TmuxSessionManager")
    def test_tmux_failure_falls_back_to_invoke(self, mock_mgr_cls: MagicMock, provider: GeminiProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-gemini-abc"
        mgr.get_or_create_session.side_effect = RuntimeError("tmux unavailable")

        # The fallback invoke() also needs mocking
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="fallback output", stderr="")
        with patch.object(provider, "run_tool", return_value=fake):
            result = provider.invoke_tmux("fix bug", "/project")
            assert result["model"] == "gemini-cli"
            assert result["output"] == "fallback output"

    @patch("runtime.providers.gemini_provider.TmuxSessionManager")
    def test_quotes_prompt_safely(self, mock_mgr_cls: MagicMock, provider: GeminiProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-gemini-abc"
        mgr.get_or_create_session.return_value = "omg-gemini-abc"
        mgr.send_command.return_value = "gemini output here"
        mgr.kill_session.return_value = True

        prompt = "it's bad; echo nope"
        provider.invoke_tmux(prompt, "/project", timeout=90)

        mgr.send_command.assert_called_once_with(
            "omg-gemini-abc",
            f"gemini -p {shlex.quote(prompt)}",
            timeout=90,
        )


# ---------------------------------------------------------------------------
# get_non_interactive_cmd
# ---------------------------------------------------------------------------

class TestGetNonInteractiveCmd:
    def test_returns_correct_cmd(self, provider: GeminiProvider) -> None:
        cmd = provider.get_non_interactive_cmd("hello world")
        assert cmd == ["gemini", "-p", "hello world"]


# ---------------------------------------------------------------------------
# get_config_path
# ---------------------------------------------------------------------------

class TestGetConfigPath:
    def test_returns_expanded_path(self, provider: GeminiProvider) -> None:
        path = provider.get_config_path()
        assert path.endswith(".gemini/settings.json")
        assert not path.startswith("~")  # must be expanded


# ---------------------------------------------------------------------------
# write_mcp_config
# ---------------------------------------------------------------------------

class TestWriteMcpConfig:
    @patch("runtime.providers.gemini_provider.write_gemini_mcp_config")
    def test_delegates_to_shared_writer(self, mock_writer: MagicMock, provider: GeminiProvider) -> None:
        with patch.object(provider, "get_config_path", return_value="/tmp/test-gemini.json"):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")
        mock_writer.assert_called_once_with(
            "http://localhost:8080",
            "test-server",
            config_path="/tmp/test-gemini.json",
        )

    @patch("runtime.providers.gemini_provider.write_gemini_mcp_config", side_effect=ValueError("invalid server_url"))
    def test_propagates_validation_error(self, _mock_writer: MagicMock, provider: GeminiProvider) -> None:
        with pytest.raises(ValueError, match="server_url"):
            provider.write_mcp_config("javascript:alert(1)")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_gemini_registered_on_import(self) -> None:
        """GeminiProvider should auto-register when the module is imported."""
        registered = get_provider("gemini")
        assert registered is not None
        assert isinstance(registered, GeminiProvider)
        assert registered.get_name() == "gemini"

    def test_gemini_in_registry_dict(self) -> None:
        assert "gemini" in _PROVIDER_REGISTRY
