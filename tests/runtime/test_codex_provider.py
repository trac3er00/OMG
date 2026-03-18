"""Tests for CodexProvider — the CLIProvider implementation for Codex CLI."""

from __future__ import annotations

import os
import shlex
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
            mock_rt.assert_called_once_with(["codex", "auth", "status"], timeout=5)
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
            mock_rt.assert_called_once_with(
                ["codex", "exec", "--json", "fix bug"],
                timeout=60,
                cwd="/project",
                env={"CLAUDE_PROJECT_DIR": "/project"},
            )
            assert result["model"] == "codex-cli"
            assert result["output"] == '{"result":"ok"}'
            assert result["exit_code"] == 0
            assert result["normalized_output"]["status"] == "ok"

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
        mgr.get_or_create_session.assert_called_once_with("omg-codex-abc", cwd="/project")
        mgr.send_command.assert_called_once()
        mgr.kill_session.assert_called_once_with("omg-codex-abc")
        assert result["model"] == "codex-cli"
        assert result["output"] == '{"done":true}'
        assert result["exit_code"] == 0
        assert result["normalized_output"]["status"] == "ok"

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

    @patch("runtime.providers.codex_provider.TmuxSessionManager")
    def test_quotes_prompt_safely(self, mock_mgr_cls: MagicMock, provider: CodexProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-codex-abc"
        mgr.get_or_create_session.return_value = "omg-codex-abc"
        mgr.send_command.return_value = "ok"
        mgr.kill_session.return_value = True

        prompt = "it's bad; echo nope"
        provider.invoke_tmux(prompt, "/project", timeout=90)

        mgr.send_command.assert_called_once_with(
            "omg-codex-abc",
            f"env CLAUDE_PROJECT_DIR={shlex.quote('/project')} codex exec --json {shlex.quote(prompt)}",
            timeout=90,
        )

    @patch("runtime.providers.codex_provider.TmuxSessionManager")
    def test_tmux_propagates_release_context(self, mock_mgr_cls: MagicMock, provider: CodexProvider, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
        monkeypatch.setenv("OMG_RUN_ID", "test-run-abc")
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-codex-abc"
        mgr.get_or_create_session.return_value = "omg-codex-abc"
        mgr.send_command.return_value = "ok"
        mgr.kill_session.return_value = True

        provider.invoke_tmux("task", "/project", timeout=60)

        cmd = mgr.send_command.call_args[0][1]
        assert "OMG_RELEASE_ORCHESTRATION_ACTIVE=1" in cmd
        assert "OMG_RUN_ID=test-run-abc" in cmd
        assert "CLAUDE_PROJECT_DIR=/project" in cmd


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
    @patch("runtime.providers.codex_provider.write_codex_mcp_config")
    def test_delegates_to_shared_writer(self, mock_writer: MagicMock, provider: CodexProvider) -> None:
        with patch.object(provider, "get_config_path", return_value="/tmp/test-codex.toml"):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")
        mock_writer.assert_called_once_with(
            "http://localhost:8080",
            "test-server",
            config_path="/tmp/test-codex.toml",
        )

    @patch("runtime.providers.codex_provider.write_codex_mcp_config", side_effect=ValueError("invalid server_name"))
    def test_propagates_validation_error(self, _mock_writer: MagicMock, provider: CodexProvider) -> None:
        with pytest.raises(ValueError, match="server_name"):
            provider.write_mcp_config("http://localhost:8080", server_name="../escape")


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
