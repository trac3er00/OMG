"""Tests for GeminiProvider — the CLIProvider implementation for Gemini CLI."""

from __future__ import annotations

import json
import os
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
    def test_writes_json_entry_new_file(self, provider: GeminiProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".gemini", "settings.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")

        assert os.path.exists(config_path)
        data = json.loads(open(config_path).read())
        assert "mcpServers" in data
        assert "test-server" in data["mcpServers"]
        assert data["mcpServers"]["test-server"]["httpUrl"] == "http://localhost:8080"

    def test_creates_parent_directory(self, provider: GeminiProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), "deep", "nested", "settings.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:9090")

        assert os.path.exists(config_path)

    def test_merges_into_existing_config(self, provider: GeminiProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".gemini", "settings.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        existing = {"mcpServers": {"old-server": {"httpUrl": "http://old:1234"}}, "otherKey": True}
        with open(config_path, "w") as fh:
            json.dump(existing, fh)

        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:5555", server_name="new-server")

        data = json.loads(open(config_path).read())
        # Old entry preserved
        assert data["mcpServers"]["old-server"]["httpUrl"] == "http://old:1234"
        # New entry added
        assert data["mcpServers"]["new-server"]["httpUrl"] == "http://localhost:5555"
        # Other keys preserved
        assert data["otherKey"] is True

    def test_uses_default_server_name(self, provider: GeminiProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".gemini", "settings.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:7777")

        data = json.loads(open(config_path).read())
        assert "memory-server" in data["mcpServers"]


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
