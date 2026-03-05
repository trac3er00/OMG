"""Tests for OpenCodeProvider -- the CLIProvider implementation for OpenCode CLI."""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from runtime.cli_provider import _PROVIDER_REGISTRY, get_provider
from runtime.providers.opencode_provider import OpenCodeProvider


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider() -> OpenCodeProvider:
    """Return a fresh OpenCodeProvider instance."""
    return OpenCodeProvider()


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

class TestGetName:
    def test_returns_opencode(self, provider: OpenCodeProvider) -> None:
        assert provider.get_name() == "opencode"


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

class TestDetect:
    @patch("shutil.which", return_value="/usr/local/bin/opencode")
    def test_returns_true_when_opencode_on_path(self, _which: MagicMock, provider: OpenCodeProvider) -> None:
        assert provider.detect() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_opencode_missing(self, _which: MagicMock, provider: OpenCodeProvider) -> None:
        assert provider.detect() is False


# ---------------------------------------------------------------------------
# check_auth
# ---------------------------------------------------------------------------

class TestCheckAuth:
    def test_returns_true_on_zero_exit(self, provider: OpenCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="authenticated\n", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            ok, msg = provider.check_auth()
            mock_rt.assert_called_once_with(["opencode", "auth", "list"], timeout=30)
            assert ok is True
            assert "authenticated" in msg

    def test_returns_false_on_nonzero_exit(self, provider: OpenCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not authenticated")
        with patch.object(provider, "run_tool", return_value=fake):
            ok, msg = provider.check_auth()
            assert ok is False

    def test_returns_none_on_exception(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("opencode")):
            ok, msg = provider.check_auth()
            assert ok is None
            assert msg  # non-empty message


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------

class TestInvoke:
    def test_success_returns_model_output_exit(self, provider: OpenCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="task completed", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke("fix bug", "/project", timeout=60)
            mock_rt.assert_called_once_with(["opencode", "run", "fix bug"], timeout=60)
            assert result == {"model": "opencode-cli", "output": "task completed", "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=120)):
            result = provider.invoke("slow task", "/project")
            assert result["error"] == "opencode-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("opencode")):
            result = provider.invoke("task", "/project")
            assert result["error"] == "opencode-cli not found"
            assert result["fallback"] == "claude"

    def test_generic_exception_returns_error_fallback(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=OSError("broken pipe")):
            result = provider.invoke("task", "/project")
            assert "broken pipe" in result["error"]
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_json
# ---------------------------------------------------------------------------

class TestInvokeJson:
    def test_success_uses_format_json_flag(self, provider: OpenCodeProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"event":"done"}', stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke_json("fix bug", "/project", timeout=90)
            mock_rt.assert_called_once_with(
                ["opencode", "run", "--format", "json", "fix bug"], timeout=90,
            )
            assert result == {"model": "opencode-cli", "output": '{"event":"done"}', "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=120)):
            result = provider.invoke_json("slow task", "/project")
            assert result["error"] == "opencode-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: OpenCodeProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("opencode")):
            result = provider.invoke_json("task", "/project")
            assert result["error"] == "opencode-cli not found"
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_tmux
# ---------------------------------------------------------------------------

class TestInvokeTmux:
    @patch("runtime.providers.opencode_provider.TmuxSessionManager")
    def test_success_returns_output(self, mock_mgr_cls: MagicMock, provider: OpenCodeProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-opencode-abc"
        mgr.get_or_create_session.return_value = "omg-opencode-abc"
        mgr.send_command.return_value = "opencode output here"
        mgr.kill_session.return_value = True

        result = provider.invoke_tmux("fix bug", "/project", timeout=90)

        mgr.make_session_name.assert_called_once()
        mgr.get_or_create_session.assert_called_once_with("omg-opencode-abc")
        mgr.send_command.assert_called_once_with(
            "omg-opencode-abc",
            ["opencode", "run", "fix bug"],
            timeout=90,
        )
        mgr.kill_session.assert_called_once_with("omg-opencode-abc")
        assert result == {"model": "opencode-cli", "output": "opencode output here", "exit_code": 0}

    @patch("runtime.providers.opencode_provider.TmuxSessionManager")
    def test_tmux_failure_falls_back_to_invoke(self, mock_mgr_cls: MagicMock, provider: OpenCodeProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-opencode-abc"
        mgr.get_or_create_session.side_effect = RuntimeError("tmux unavailable")

        # The fallback invoke() also needs mocking
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="fallback output", stderr="")
        with patch.object(provider, "run_tool", return_value=fake):
            result = provider.invoke_tmux("fix bug", "/project")
            assert result["model"] == "opencode-cli"
            assert result["output"] == "fallback output"


# ---------------------------------------------------------------------------
# get_non_interactive_cmd
# ---------------------------------------------------------------------------

class TestGetNonInteractiveCmd:
    def test_returns_correct_cmd(self, provider: OpenCodeProvider) -> None:
        cmd = provider.get_non_interactive_cmd("hello world")
        assert cmd == ["opencode", "run", "hello world"]


# ---------------------------------------------------------------------------
# get_config_path
# ---------------------------------------------------------------------------

class TestGetConfigPath:
    def test_returns_expanded_path(self, provider: OpenCodeProvider) -> None:
        path = provider.get_config_path()
        assert path.endswith(".config/opencode/opencode.json")
        assert not path.startswith("~")  # must be expanded


# ---------------------------------------------------------------------------
# write_mcp_config
# ---------------------------------------------------------------------------

class TestWriteMcpConfig:
    def test_writes_json_entry_new_file(self, provider: OpenCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".config", "opencode", "opencode.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")

        assert os.path.exists(config_path)
        data = json.loads(open(config_path).read())
        assert "mcp" in data
        assert "test-server" in data["mcp"]
        assert data["mcp"]["test-server"]["type"] == "remote"
        assert data["mcp"]["test-server"]["url"] == "http://localhost:8080"

    def test_creates_parent_directory(self, provider: OpenCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), "deep", "nested", "opencode.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:9090")

        assert os.path.exists(config_path)

    def test_merges_into_existing_config(self, provider: OpenCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".config", "opencode", "opencode.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        existing = {"mcp": {"old-server": {"type": "remote", "url": "http://old:1234"}}, "otherKey": True}
        with open(config_path, "w") as fh:
            json.dump(existing, fh)

        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:5555", server_name="new-server")

        data = json.loads(open(config_path).read())
        # Old entry preserved
        assert data["mcp"]["old-server"]["url"] == "http://old:1234"
        # New entry added
        assert data["mcp"]["new-server"]["type"] == "remote"
        assert data["mcp"]["new-server"]["url"] == "http://localhost:5555"
        # Other keys preserved
        assert data["otherKey"] is True

    def test_uses_default_server_name(self, provider: OpenCodeProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".config", "opencode", "opencode.json")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:7777")

        data = json.loads(open(config_path).read())
        assert "memory-server" in data["mcp"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_opencode_registered_on_import(self) -> None:
        """OpenCodeProvider should auto-register when the module is imported."""
        registered = get_provider("opencode")
        assert registered is not None
        assert isinstance(registered, OpenCodeProvider)
        assert registered.get_name() == "opencode"

    def test_opencode_in_registry_dict(self) -> None:
        assert "opencode" in _PROVIDER_REGISTRY
