"""Tests for KimiCodeProvider -- the CLIProvider implementation for Kimi Code CLI."""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from runtime.cli_provider import _PROVIDER_REGISTRY, get_provider
from runtime.providers.kimi_provider import KimiCodeProvider


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider() -> KimiCodeProvider:
    """Return a fresh KimiCodeProvider instance."""
    return KimiCodeProvider()


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

class TestGetName:
    def test_returns_kimi(self, provider: KimiCodeProvider) -> None:
        assert provider.get_name() == "kimi"


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

class TestDetect:
    @patch("shutil.which", return_value="/usr/local/bin/kimi")
    def test_returns_true_when_kimi_on_path(self, _which: MagicMock, provider: KimiCodeProvider) -> None:
        assert provider.detect() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_kimi_missing(self, _which: MagicMock, provider: KimiCodeProvider) -> None:
        assert provider.detect() is False


# ---------------------------------------------------------------------------
# check_auth
# ---------------------------------------------------------------------------

class TestCheckAuth:
    def test_returns_true_when_config_has_token(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_dir = os.path.join(str(tmp_path), ".kimi")
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, "config.toml")
        with open(config_file, "w") as fh:
            fh.write('[auth]\ntoken = "sk-abc123"\n')

        with patch("os.path.expanduser", return_value=config_file):
            ok, msg = provider.check_auth()
            assert ok is True
            assert "authenticated" in msg

    def test_returns_false_when_config_missing(self, provider: KimiCodeProvider) -> None:
        with patch("os.path.expanduser", return_value="/nonexistent/.kimi/config.toml"):
            ok, msg = provider.check_auth()
            assert ok is False
            assert "not authenticated" in msg

    def test_returns_false_when_config_has_no_token(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_dir = os.path.join(str(tmp_path), ".kimi")
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, "config.toml")
        with open(config_file, "w") as fh:
            fh.write("[settings]\ntheme = dark\n")

        with patch("os.path.expanduser", return_value=config_file):
            ok, msg = provider.check_auth()
            assert ok is False
            assert "not authenticated" in msg

    def test_returns_none_on_exception(self, provider: KimiCodeProvider) -> None:
        with patch("os.path.expanduser", side_effect=RuntimeError("os error")):
            ok, msg = provider.check_auth()
            assert ok is None
            assert msg  # non-empty message


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------

class TestInvoke:
    def test_success_returns_model_output_exit(self, provider: KimiCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="task completed", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke("fix bug", "/project", timeout=60)
            mock_rt.assert_called_once_with(["kimi", "--print", "-p", "fix bug"], timeout=60)
            assert result == {"model": "kimi-cli", "output": "task completed", "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="kimi", timeout=120)):
            result = provider.invoke("slow task", "/project")
            assert result["error"] == "kimi-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("kimi")):
            result = provider.invoke("task", "/project")
            assert result["error"] == "kimi-cli not found"
            assert result["fallback"] == "claude"

    def test_generic_exception_returns_error_fallback(self, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=OSError("broken pipe")):
            result = provider.invoke("task", "/project")
            assert "broken pipe" in result["error"]
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_json
# ---------------------------------------------------------------------------

class TestInvokeJson:
    def test_success_uses_stream_json_flag(self, provider: KimiCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"event":"done"}', stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke_json("fix bug", "/project", timeout=90)
            mock_rt.assert_called_once_with(
                ["kimi", "--print", "--output-format", "stream-json", "-p", "fix bug"], timeout=90,
            )
            assert result == {"model": "kimi-cli", "output": '{"event":"done"}', "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="kimi", timeout=120)):
            result = provider.invoke_json("slow task", "/project")
            assert result["error"] == "kimi-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("kimi")):
            result = provider.invoke_json("task", "/project")
            assert result["error"] == "kimi-cli not found"
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_tmux
# ---------------------------------------------------------------------------

class TestInvokeTmux:
    @patch("runtime.providers.kimi_provider.TmuxSessionManager")
    def test_success_returns_output(self, mock_mgr_cls: MagicMock, provider: KimiCodeProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-kimi-abc"
        mgr.get_or_create_session.return_value = "omg-kimi-abc"
        mgr.send_command.return_value = "kimi output here"
        mgr.kill_session.return_value = True

        result = provider.invoke_tmux("fix bug", "/project", timeout=90)

        mgr.make_session_name.assert_called_once()
        mgr.get_or_create_session.assert_called_once_with("omg-kimi-abc")
        mgr.send_command.assert_called_once()
        mgr.kill_session.assert_called_once_with("omg-kimi-abc")
        assert result == {"model": "kimi-cli", "output": "kimi output here", "exit_code": 0}

    @patch("runtime.providers.kimi_provider.TmuxSessionManager")
    def test_tmux_failure_falls_back_to_invoke(self, mock_mgr_cls: MagicMock, provider: KimiCodeProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-kimi-abc"
        mgr.get_or_create_session.side_effect = RuntimeError("tmux unavailable")

        # The fallback invoke() also needs mocking
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="fallback output", stderr="")
        with patch.object(provider, "run_tool", return_value=fake):
            result = provider.invoke_tmux("fix bug", "/project")
            assert result["model"] == "kimi-cli"
            assert result["output"] == "fallback output"


# ---------------------------------------------------------------------------
# get_non_interactive_cmd
# ---------------------------------------------------------------------------

class TestGetNonInteractiveCmd:
    def test_returns_correct_cmd(self, provider: KimiCodeProvider) -> None:
        cmd = provider.get_non_interactive_cmd("hello world")
        assert cmd == ["kimi", "--print", "-p", "hello world"]


# ---------------------------------------------------------------------------
# get_config_path
# ---------------------------------------------------------------------------

class TestGetConfigPath:
    def test_returns_expanded_path(self, provider: KimiCodeProvider) -> None:
        path = provider.get_config_path()
        assert path.endswith(".kimi/mcp.json")
        assert not path.startswith("~")  # must be expanded


# ---------------------------------------------------------------------------
# write_mcp_config
# ---------------------------------------------------------------------------

class TestWriteMcpConfig:
    def test_writes_json_entry_new_file(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".kimi", "mcp.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")

        assert os.path.exists(config_path)
        data = json.loads(open(config_path).read())
        assert "mcpServers" in data
        assert "test-server" in data["mcpServers"]
        assert data["mcpServers"]["test-server"]["type"] == "http"
        assert data["mcpServers"]["test-server"]["url"] == "http://localhost:8080"

    def test_creates_parent_directory(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), "deep", "nested", "mcp.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:9090")

        assert os.path.exists(config_path)

    def test_merges_into_existing_config(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".kimi", "mcp.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        existing = {"mcpServers": {"old-server": {"type": "http", "url": "http://old:1234"}}, "otherKey": True}
        with open(config_path, "w") as fh:
            json.dump(existing, fh)

        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:5555", server_name="new-server")

        data = json.loads(open(config_path).read())
        # Old entry preserved
        assert data["mcpServers"]["old-server"]["url"] == "http://old:1234"
        # New entry added
        assert data["mcpServers"]["new-server"]["type"] == "http"
        assert data["mcpServers"]["new-server"]["url"] == "http://localhost:5555"
        # Other keys preserved
        assert data["otherKey"] is True

    def test_uses_default_server_name(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".kimi", "mcp.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:7777")

        data = json.loads(open(config_path).read())
        assert "memory-server" in data["mcpServers"]

    def test_handles_corrupt_json_gracefully(self, provider: KimiCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".kimi", "mcp.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as fh:
            fh.write("{corrupted json!!")

        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:6666", server_name="fresh")

        data = json.loads(open(config_path).read())
        assert data["mcpServers"]["fresh"]["url"] == "http://localhost:6666"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_kimi_registered_on_import(self) -> None:
        """KimiCodeProvider should auto-register when the module is imported."""
        registered = get_provider("kimi")
        assert registered is not None
        assert isinstance(registered, KimiCodeProvider)
        assert registered.get_name() == "kimi"

    def test_kimi_in_registry_dict(self) -> None:
        assert "kimi" in _PROVIDER_REGISTRY
