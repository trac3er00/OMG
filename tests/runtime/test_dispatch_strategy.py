"""Tests for dispatch strategy detection and reporting (NF7e).

Tests the hybrid dispatch strategy selection: Agent > tmux > subprocess.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load module via path — use unique name + register in sys.modules to avoid
# Python 3.13 dataclass introspection crash (needs __module__ in sys.modules).
import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MOD_PATH = _REPO_ROOT / "runtime" / "team_router.py"
_MOD_NAME = "runtime_team_router_dispatch_tests"
spec = importlib.util.spec_from_file_location(_MOD_NAME, _MOD_PATH)
assert spec is not None and spec.loader is not None
_mod = importlib.util.module_from_spec(spec)
_sys.modules[_MOD_NAME] = _mod
spec.loader.exec_module(_mod)

# Import constants and functions from the loaded module
DISPATCH_AGENT = _mod.DISPATCH_AGENT
DISPATCH_TMUX = _mod.DISPATCH_TMUX
DISPATCH_THREAD = _mod.DISPATCH_THREAD
detect_dispatch_strategy = _mod.detect_dispatch_strategy
dispatch_strategy_report = _mod.dispatch_strategy_report


class TestDispatchStrategyConstants:
    """Test dispatch strategy constants are properly defined."""

    def test_dispatch_agent_value(self):
        """DISPATCH_AGENT has expected value."""
        assert DISPATCH_AGENT == "agent-tool"

    def test_dispatch_tmux_value(self):
        """DISPATCH_TMUX has expected value."""
        assert DISPATCH_TMUX == "tmux-session"

    def test_dispatch_thread_value(self):
        """DISPATCH_THREAD has expected value."""
        assert DISPATCH_THREAD == "thread-pool"


class TestDetectDispatchStrategy:
    """Test detect_dispatch_strategy() function."""

    def test_returns_agent_tool_when_claude_code_env_set(self):
        """Returns agent-tool when CLAUDE_CODE env var is set."""
        with patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=False):
            # Also ensure no CLAUDE_CODE_ENTRYPOINT to isolate the test
            env_copy = os.environ.copy()
            env_copy.pop("CLAUDE_CODE_ENTRYPOINT", None)
            env_copy["CLAUDE_CODE"] = "1"
            with patch.dict(os.environ, env_copy, clear=True):
                result = detect_dispatch_strategy()
                assert result == DISPATCH_AGENT

    def test_returns_agent_tool_when_claude_code_entrypoint_set(self):
        """Returns agent-tool when CLAUDE_CODE_ENTRYPOINT env var is set."""
        with patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "/path/to/entrypoint"}, clear=False):
            env_copy = os.environ.copy()
            env_copy.pop("CLAUDE_CODE", None)
            env_copy["CLAUDE_CODE_ENTRYPOINT"] = "/path/to/entrypoint"
            with patch.dict(os.environ, env_copy, clear=True):
                result = detect_dispatch_strategy()
                assert result == DISPATCH_AGENT

    def test_returns_tmux_session_when_tmux_available(self):
        """Returns tmux-session when tmux is available and not in Claude Code."""
        # Clear Claude Code env vars and mock tmux as available
        env_without_claude = {k: v for k, v in os.environ.items()
                             if k not in ("CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")}
        with patch.dict(os.environ, env_without_claude, clear=True):
            with patch.object(_mod, "_is_tmux_available", return_value=True):
                result = detect_dispatch_strategy()
                assert result == DISPATCH_TMUX

    def test_returns_thread_pool_as_fallback(self):
        """Returns thread-pool when neither Claude Code nor tmux available."""
        env_without_claude = {k: v for k, v in os.environ.items()
                             if k not in ("CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")}
        with patch.dict(os.environ, env_without_claude, clear=True):
            with patch.object(_mod, "_is_tmux_available", return_value=False):
                result = detect_dispatch_strategy()
                assert result == DISPATCH_THREAD

    def test_agent_tool_takes_priority_over_tmux(self):
        """Agent-tool strategy takes priority even when tmux is available."""
        with patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=False):
            with patch.object(_mod, "_is_tmux_available", return_value=True):
                result = detect_dispatch_strategy()
                assert result == DISPATCH_AGENT


class TestDispatchStrategyReport:
    """Test dispatch_strategy_report() function."""

    def test_agent_tool_report_structure(self):
        """Agent-tool report has correct structure."""
        report = dispatch_strategy_report(DISPATCH_AGENT)
        assert report["strategy"] == "agent-tool"
        assert report["parallel"] is True
        assert report["shared_context"] is True
        assert report["providers"] == ["claude"]

    def test_tmux_session_report_structure(self):
        """Tmux-session report has correct structure."""
        report = dispatch_strategy_report(DISPATCH_TMUX)
        assert report["strategy"] == "tmux-session"
        assert report["parallel"] is True
        assert report["shared_context"] is False
        assert report["providers"] == ["codex", "gemini", "kimi", "claude"]

    def test_thread_pool_report_structure(self):
        """Thread-pool report has correct structure."""
        report = dispatch_strategy_report(DISPATCH_THREAD)
        assert report["strategy"] == "thread-pool"
        assert report["parallel"] is True
        assert report["shared_context"] is False
        assert report["providers"] == ["codex", "gemini", "kimi"]

    def test_unknown_strategy_defaults_to_thread_pool(self):
        """Unknown strategy value defaults to thread-pool report."""
        report = dispatch_strategy_report("unknown-strategy")
        assert report["strategy"] == "thread-pool"
        assert report["parallel"] is True
        assert report["shared_context"] is False

    def test_report_keys_present(self):
        """All reports contain required keys."""
        required_keys = {"strategy", "parallel", "shared_context", "providers"}
        for strategy in [DISPATCH_AGENT, DISPATCH_TMUX, DISPATCH_THREAD]:
            report = dispatch_strategy_report(strategy)
            assert required_keys <= set(report.keys()), f"Missing keys in {strategy} report"

    def test_providers_is_list(self):
        """Providers field is always a list."""
        for strategy in [DISPATCH_AGENT, DISPATCH_TMUX, DISPATCH_THREAD]:
            report = dispatch_strategy_report(strategy)
            assert isinstance(report["providers"], list)


class TestDispatchStrategyIntegration:
    """Integration tests for dispatch strategy in execute functions."""

    def test_detect_and_report_consistency(self):
        """detect_dispatch_strategy result works with dispatch_strategy_report."""
        # Clear Claude Code env vars and mock tmux as unavailable
        env_without_claude = {k: v for k, v in os.environ.items()
                             if k not in ("CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")}
        with patch.dict(os.environ, env_without_claude, clear=True):
            with patch.object(_mod, "_is_tmux_available", return_value=False):
                strategy = detect_dispatch_strategy()
                report = dispatch_strategy_report(strategy)
                assert report["strategy"] == strategy
