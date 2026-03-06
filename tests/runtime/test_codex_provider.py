"""Tests for CodexProvider — the CLIProvider implementation for Codex CLI."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from runtime.cli_provider import _PROVIDER_REGISTRY, get_provider
from runtime.providers.codex_provider import CodexProvider


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider() -> CodexProvider:
    """Return a fresh CodexProvider instance."""
    return CodexProvider()


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

class TestGetName:
    def test_returns_codex(self, provider: CodexProvider) -> None:
        assert provider.get_name() == "codex"


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

class TestDetect:
    @patch("shutil.which", return_value="/usr/local/bin/codex")
    def test_returns_true_when_codex_on_path(self, _which: MagicMock, provider: CodexProvider) -> None:
        assert provider.detect() is True

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_codex_missing(self, _which: MagicMock, provider: CodexProvider) -> None:
        assert provider.detect() is False


# ---------------------------------------------------------------------------
# check_auth
# ---------------------------------------------------------------------------

class TestCheckAuth:
    def test_returns_true_on_zero_exit(self, provider: CodexProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="authenticated\n", stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            ok, msg = provider.check_auth()
            mock_rt.assert_called_once_with(["codex", "auth", "status"], timeout=30)
            assert ok is True
            assert "authenticated" in msg

    def test_returns_false_on_nonzero_exit(self, provider: CodexProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not logged in")
        with patch.object(provider, "run_tool", return_value=fake):
            ok, msg = provider.check_auth()
            assert ok is False

    def test_returns_none_on_exception(self, provider: CodexProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("codex")):
            ok, msg = provider.check_auth()
            assert ok is None
            assert msg  # non-empty message


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------

class TestInvoke:
    def test_success_returns_model_output_exit(self, provider: CodexProvider) -> None:
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"result":"ok"}', stderr="")
        with patch.object(provider, "run_tool", return_value=fake) as mock_rt:
            result = provider.invoke("fix bug", "/project", timeout=60)
            mock_rt.assert_called_once_with(["codex", "exec", "--json", "fix bug"], timeout=60)
            assert result == {"model": "codex-cli", "output": '{"result":"ok"}', "exit_code": 0}

    def test_timeout_returns_error_fallback(self, provider: CodexProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=120)):
            result = provider.invoke("slow task", "/project")
            assert result["error"] == "codex-cli timeout"
            assert result["fallback"] == "claude"

    def test_file_not_found_returns_error_fallback(self, provider: CodexProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=FileNotFoundError("codex")):
            result = provider.invoke("task", "/project")
            assert result["error"] == "codex-cli not found"
            assert result["fallback"] == "claude"

    def test_generic_exception_returns_error_fallback(self, provider: CodexProvider) -> None:
        with patch.object(provider, "run_tool", side_effect=OSError("broken pipe")):
            result = provider.invoke("task", "/project")
            assert "broken pipe" in result["error"]
            assert result["fallback"] == "claude"


# ---------------------------------------------------------------------------
# invoke_tmux
# ---------------------------------------------------------------------------

class TestInvokeTmux:
    @patch("runtime.providers.codex_provider.TmuxSessionManager")
    def test_success_returns_output(self, mock_mgr_cls: MagicMock, provider: CodexProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-codex-abc"
        mgr.get_or_create_session.return_value = "omg-codex-abc"
        mgr.send_command.return_value = '{"done":true}'
        mgr.kill_session.return_value = True

        result = provider.invoke_tmux("fix bug", "/project", timeout=90)

        mgr.make_session_name.assert_called_once()
        mgr.get_or_create_session.assert_called_once_with("omg-codex-abc")
        mgr.send_command.assert_called_once()
        mgr.kill_session.assert_called_once_with("omg-codex-abc")
        assert result == {"model": "codex-cli", "output": '{"done":true}', "exit_code": 0}

    @patch("runtime.providers.codex_provider.TmuxSessionManager")
    def test_tmux_failure_falls_back_to_invoke(self, mock_mgr_cls: MagicMock, provider: CodexProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-codex-abc"
        mgr.get_or_create_session.side_effect = RuntimeError("tmux unavailable")

        # The fallback invoke() also needs mocking
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="fallback output", stderr="")
        with patch.object(provider, "run_tool", return_value=fake):
            result = provider.invoke_tmux("fix bug", "/project")
            assert result["model"] == "codex-cli"
            assert result["output"] == "fallback output"


# ---------------------------------------------------------------------------
# get_non_interactive_cmd
# ---------------------------------------------------------------------------

class TestGetNonInteractiveCmd:
    def test_returns_correct_cmd(self, provider: CodexProvider) -> None:
        cmd = provider.get_non_interactive_cmd("hello world")
        assert cmd == ["codex", "exec", "--json", "hello world"]


# ---------------------------------------------------------------------------
# get_config_path
# ---------------------------------------------------------------------------

class TestGetConfigPath:
    def test_returns_expanded_path(self, provider: CodexProvider) -> None:
        path = provider.get_config_path()
        assert path.endswith(".codex/config.toml")
        assert not path.startswith("~")  # must be expanded


# ---------------------------------------------------------------------------
# write_mcp_config
# ---------------------------------------------------------------------------

class TestWriteMcpConfig:
    def test_writes_toml_entry(self, provider: CodexProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), ".codex", "config.toml")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")

        assert os.path.exists(config_path)
        content = open(config_path).read()
        assert "test-server" in content
        assert "http://localhost:8080" in content

    def test_creates_parent_directory(self, provider: CodexProvider, tmp_path: object) -> None:
        config_path = os.path.join(str(tmp_path), "deep", "nested", "config.toml")
        with patch.object(provider, "get_config_path", return_value=config_path):
            provider.write_mcp_config("http://localhost:9090")

        assert os.path.exists(config_path)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_codex_registered_on_import(self) -> None:
        """CodexProvider should auto-register when the module is imported."""
        registered = get_provider("codex")
        assert registered is not None
        assert isinstance(registered, CodexProvider)
        assert registered.get_name() == "codex"

    def test_codex_in_registry_dict(self) -> None:
        assert "codex" in _PROVIDER_REGISTRY
