"""Tests for NF5c (selective agent-as-tool) and NF5d (native sub-agent API support)."""
from __future__ import annotations

import os
import sys
import pytest

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from runtime.router_selector import (
    score_task_complexity,
    should_use_subagent,
)
from runtime.subagent_dispatcher import (
    is_native_subagent_available,
    build_native_subagent_instruction,
    get_dispatch_mode,
)


# =============================================================================
# NF5c: score_task_complexity Tests
# =============================================================================


class TestScoreTaskComplexity:
    """Tests for score_task_complexity() function."""

    def test_low_risk_low_ambiguity_returns_direct(self):
        """Simple, clear task with files returns 'direct' recommendation."""
        result = score_task_complexity(
            "update the button color in header",
            files=["src/Header.tsx", "src/styles.css"],
        )
        assert result["risk"] < 0.3
        assert result["ambiguity"] < 0.3
        assert result["recommendation"] == "direct"

    def test_security_keywords_increase_risk(self):
        """Security keywords increase risk score."""
        result = score_task_complexity(
            "fix the authentication vulnerability in the JWT token handling",
            files=["src/auth.py"],
        )
        # auth (+0.3) + authentication (+0.3) + vulnerability (+0.3) + jwt (+0.3) + token (+0.3)
        assert result["risk"] >= 0.6
        assert result["recommendation"] in ("isolated", "ccg")

    def test_crypto_keyword_increases_risk(self):
        """Crypto-related keywords increase risk."""
        result = score_task_complexity(
            "implement encryption for user passwords with crypto library",
            files=["src/crypto.py"],
        )
        # encryption (+0.3) + password (+0.3) + crypto (+0.3)
        assert result["risk"] >= 0.6

    def test_migration_keywords_increase_risk(self):
        """Migration and infrastructure keywords increase risk."""
        result = score_task_complexity(
            "migrate database schema for production deployment",
            files=["migrations/001.sql"],
        )
        # migrate (+0.2) + database (+0.2) + schema (+0.2) + production (+0.2)
        assert result["risk"] >= 0.3
        assert result["recommendation"] in ("isolated", "ccg")

    def test_many_files_increase_risk(self):
        """More than 5 files increases risk by 0.2."""
        result = score_task_complexity(
            "update logging statements",
            files=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
        )
        assert result["risk"] >= 0.2

    def test_vague_prompt_increases_ambiguity(self):
        """Vague keywords increase ambiguity score."""
        result = score_task_complexity(
            "fix something somehow in the code maybe",
            files=["main.py"],
        )
        # something (+0.3) + somehow (+0.3) + maybe (+0.3)
        assert result["ambiguity"] >= 0.6

    def test_broad_scope_words_increase_ambiguity(self):
        """Broad scope words like 'everything' increase ambiguity."""
        result = score_task_complexity(
            "refactor everything in the entire codebase",
            files=["src/app.py"],
        )
        # everything (+0.2) + entire (+0.2)
        assert result["ambiguity"] >= 0.3
        assert result["recommendation"] in ("isolated", "ccg")

    def test_no_files_increases_ambiguity(self):
        """No files specified increases ambiguity by 0.2."""
        result = score_task_complexity("fix the bug in the login form")
        assert result["ambiguity"] >= 0.2

    def test_short_prompt_increases_ambiguity(self):
        """Short prompts (< 5 words) increase ambiguity by 0.3."""
        result = score_task_complexity("fix it", files=["main.py"])
        # short prompt (+0.3)
        assert result["ambiguity"] >= 0.3

    def test_high_risk_high_ambiguity_returns_ccg(self):
        """High risk AND high ambiguity returns 'ccg' recommendation."""
        result = score_task_complexity(
            "fix everything related to security and authentication somehow"
        )
        # security (+0.3), auth (+0.3) = risk >= 0.6
        # everything (+0.2), somehow (+0.3), no files (+0.2) = ambiguity >= 0.6
        assert result["risk"] >= 0.6
        assert result["ambiguity"] >= 0.6
        assert result["recommendation"] == "ccg"

    def test_moderate_risk_returns_isolated(self):
        """Moderate risk (>= 0.3) with low ambiguity returns 'isolated'."""
        result = score_task_complexity(
            "add rate limiting to the authentication endpoint",
            files=["src/auth.py", "src/middleware.py"],
        )
        # auth/authentication boosts risk
        assert result["risk"] >= 0.3
        assert result["recommendation"] in ("isolated", "ccg")

    def test_scores_capped_at_1(self):
        """Risk and ambiguity scores are capped at 1.0."""
        result = score_task_complexity(
            "fix security auth crypto password token jwt oauth vulnerability exploit injection xss csrf something somehow maybe whatever"
        )
        assert result["risk"] <= 1.0
        assert result["ambiguity"] <= 1.0


# =============================================================================
# NF5c: should_use_subagent Tests
# =============================================================================


class TestShouldUseSubagent:
    """Tests for should_use_subagent() convenience function."""

    def test_returns_false_for_simple_tasks(self):
        """Returns False for simple, low-risk, low-ambiguity tasks."""
        result = should_use_subagent(
            "update the button text in the header component",
            files=["src/Header.tsx", "src/Button.tsx"],
        )
        assert result is False

    def test_returns_true_for_complex_tasks(self):
        """Returns True for complex tasks requiring sub-agent."""
        result = should_use_subagent(
            "audit security vulnerabilities in authentication system"
        )
        assert result is True

    def test_returns_true_for_ambiguous_tasks(self):
        """Returns True for ambiguous tasks."""
        result = should_use_subagent("fix everything somehow")
        assert result is True

    def test_returns_true_for_risky_tasks(self):
        """Returns True for risky tasks even with low ambiguity."""
        result = should_use_subagent(
            "implement JWT token rotation for OAuth authentication",
            files=["src/auth.py"],
        )
        assert result is True


# =============================================================================
# NF5d: is_native_subagent_available Tests
# =============================================================================


class TestIsNativeSubagentAvailable:
    """Tests for is_native_subagent_available() function."""

    def test_returns_false_when_flag_not_set(self, monkeypatch):
        """Returns False when OMG_NATIVE_SUBAGENTS is not set."""
        monkeypatch.delenv("OMG_NATIVE_SUBAGENTS", raising=False)
        monkeypatch.delenv("CLAUDE_CODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        assert is_native_subagent_available() is False

    def test_returns_false_when_flag_is_zero(self, monkeypatch):
        """Returns False when OMG_NATIVE_SUBAGENTS is '0'."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "0")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert is_native_subagent_available() is False

    def test_returns_false_when_flag_is_false(self, monkeypatch):
        """Returns False when OMG_NATIVE_SUBAGENTS is 'false'."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "false")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert is_native_subagent_available() is False

    def test_returns_false_without_claude_code(self, monkeypatch):
        """Returns False when flag is set but CLAUDE_CODE is not."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "1")
        monkeypatch.delenv("CLAUDE_CODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        assert is_native_subagent_available() is False

    def test_returns_true_with_claude_code(self, monkeypatch):
        """Returns True when flag is set and CLAUDE_CODE exists."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "1")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert is_native_subagent_available() is True

    def test_returns_true_with_claude_code_entrypoint(self, monkeypatch):
        """Returns True when flag is set and CLAUDE_CODE_ENTRYPOINT exists."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "true")
        monkeypatch.delenv("CLAUDE_CODE", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "/usr/bin/claude")
        assert is_native_subagent_available() is True

    def test_flag_case_insensitive(self, monkeypatch):
        """Flag checking is case-insensitive."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "TRUE")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert is_native_subagent_available() is True


# =============================================================================
# NF5d: build_native_subagent_instruction Tests
# =============================================================================


class TestBuildNativeSubagentInstruction:
    """Tests for build_native_subagent_instruction() function."""

    def test_returns_correct_structure(self):
        """Returns dict with required keys."""
        result = build_native_subagent_instruction("codex", "analyze the code")
        assert result["tool"] == "Agent"
        assert result["subagent_type"] == "codex"
        assert result["prompt"] == "analyze the code"
        assert result["run_in_background"] is True

    def test_background_default_true(self):
        """run_in_background defaults to True."""
        result = build_native_subagent_instruction("gemini", "review UI")
        assert result["run_in_background"] is True

    def test_background_can_be_false(self):
        """run_in_background can be set to False."""
        result = build_native_subagent_instruction("task", "quick check", background=False)
        assert result["run_in_background"] is False

    def test_preserves_agent_type(self):
        """Agent type is preserved exactly."""
        for agent_type in ["codex", "gemini", "task", "custom-agent"]:
            result = build_native_subagent_instruction(agent_type, "test")
            assert result["subagent_type"] == agent_type

    def test_preserves_prompt_exactly(self):
        """Prompt is preserved exactly without modification."""
        prompt = "analyze security vulnerabilities in auth/login.py"
        result = build_native_subagent_instruction("codex", prompt)
        assert result["prompt"] == prompt


# =============================================================================
# NF5d: get_dispatch_mode Tests
# =============================================================================


class TestGetDispatchMode:
    """Tests for get_dispatch_mode() function."""

    def test_returns_cli_when_native_unavailable(self, monkeypatch):
        """Returns 'cli' when native sub-agents are unavailable."""
        monkeypatch.delenv("OMG_NATIVE_SUBAGENTS", raising=False)
        monkeypatch.delenv("CLAUDE_CODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        assert get_dispatch_mode() == "cli"

    def test_returns_native_when_available(self, monkeypatch):
        """Returns 'native' when native sub-agents are available."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "1")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert get_dispatch_mode() == "native"

    def test_returns_cli_when_flag_disabled(self, monkeypatch):
        """Returns 'cli' when flag is disabled even with CLAUDE_CODE."""
        monkeypatch.setenv("OMG_NATIVE_SUBAGENTS", "0")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        assert get_dispatch_mode() == "cli"
