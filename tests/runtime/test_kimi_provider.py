"""Tests for KimiCodeProvider -- the CLIProvider implementation for Kimi Code CLI."""

from __future__ import annotations

import json
import os
import shlex
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
            mock_rt.assert_called_once_with(
                ["kimi", "--print", "-p", "fix bug"],
                timeout=60,
                cwd="/project",
                env={"CLAUDE_PROJECT_DIR": "/project"},
            )
            assert result["model"] == "kimi-cli"
            assert result["output"] == "task completed"
            assert result["exit_code"] == 0
            assert result["normalized_output"]["status"] == "ok"

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
                ["kimi", "--print", "--output-format", "stream-json", "-p", "fix bug"],
                timeout=90,
                cwd="/project",
                env={"CLAUDE_PROJECT_DIR": "/project"},
            )
            assert result["model"] == "kimi-cli"
            assert result["output"] == '{"event":"done"}'
            assert result["exit_code"] == 0
            assert result["normalized_output"]["status"] == "ok"

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
        mgr.get_or_create_session.assert_called_once_with("omg-kimi-abc", cwd="/project")
        mgr.send_command.assert_called_once()
        mgr.kill_session.assert_called_once_with("omg-kimi-abc")
        assert result["model"] == "kimi-cli"
        assert result["output"] == "kimi output here"
        assert result["exit_code"] == 0
        assert result["normalized_output"]["status"] == "ok"

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

    @patch("runtime.providers.kimi_provider.TmuxSessionManager")
    def test_quotes_prompt_safely(self, mock_mgr_cls: MagicMock, provider: KimiCodeProvider) -> None:
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-kimi-abc"
        mgr.get_or_create_session.return_value = "omg-kimi-abc"
        mgr.send_command.return_value = "kimi output here"
        mgr.kill_session.return_value = True

        prompt = "it's bad; echo nope"
        provider.invoke_tmux(prompt, "/project", timeout=90)

        mgr.send_command.assert_called_once_with(
            "omg-kimi-abc",
            f"env CLAUDE_PROJECT_DIR={shlex.quote('/project')} kimi --print -p {shlex.quote(prompt)}",
            timeout=90,
        )

    @patch("runtime.providers.kimi_provider.TmuxSessionManager")
    def test_tmux_propagates_release_context(self, mock_mgr_cls: MagicMock, provider: KimiCodeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_RELEASE_ORCHESTRATION_ACTIVE", "1")
        monkeypatch.setenv("OMG_RUN_ID", "test-run-abc")
        mgr = mock_mgr_cls.return_value
        mgr.make_session_name.return_value = "omg-kimi-abc"
        mgr.get_or_create_session.return_value = "omg-kimi-abc"
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
    @patch("runtime.providers.kimi_provider.write_kimi_mcp_config")
    def test_delegates_to_shared_writer(self, mock_writer: MagicMock, provider: KimiCodeProvider) -> None:
        with patch.object(provider, "get_config_path", return_value="/tmp/test-kimi.json"):
            provider.write_mcp_config("http://localhost:8080", server_name="test-server")
        mock_writer.assert_called_once_with(
            "http://localhost:8080",
            "test-server",
            config_path="/tmp/test-kimi.json",
        )

    @patch("runtime.providers.kimi_provider.write_kimi_mcp_config", side_effect=ValueError("invalid server_name"))
    def test_propagates_validation_error(self, _mock_writer: MagicMock, provider: KimiCodeProvider) -> None:
        with pytest.raises(ValueError, match="server_name"):
            provider.write_mcp_config("http://localhost:8080", server_name="../escape")


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
