"""Tests for task-type routing in router_selector.py (NF5a)."""
from __future__ import annotations

import os
import sys
import pytest

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from runtime.router_selector import (
    TASK_TYPES,
    classify_task_type,
    get_routing_for_task,
)


# =============================================================================
# TASK_TYPES Configuration Tests
# =============================================================================


class TestTaskTypesConfig:
    """Tests for TASK_TYPES configuration."""

    def test_task_types_has_required_keys(self):
        """TASK_TYPES contains all expected task types."""
        expected = {"feature", "bugfix", "security", "ui-change", "refactor", "docs", "migration"}
        assert set(TASK_TYPES.keys()) == expected

    def test_each_task_type_has_routing_config(self):
        """Each task type has primary, fallback, strategy, and gate keys."""
        for task_type, config in TASK_TYPES.items():
            assert "primary" in config, f"{task_type} missing primary"
            assert "fallback" in config, f"{task_type} missing fallback"
            assert "strategy" in config, f"{task_type} missing strategy"
            assert "gate" in config, f"{task_type} missing gate"

    def test_security_has_hard_gate(self):
        """Security task type has hard gate."""
        assert TASK_TYPES["security"]["gate"] == "hard"


# =============================================================================
# classify_task_type Tests
# =============================================================================


class TestClassifyTaskType:
    """Tests for classify_task_type() function."""

    def test_bugfix_from_prompt(self):
        """Prompt with 'fix' and 'bug' classifies as bugfix."""
        result = classify_task_type("fix the login bug")
        assert result["task_type"] == "bugfix"
        assert result["confidence"] > 0
        assert any("keyword:" in s for s in result["signals"])

    def test_ui_change_from_files(self):
        """Prompt with UI files classifies as ui-change."""
        result = classify_task_type("add dark mode toggle", files=["src/App.tsx"])
        assert result["task_type"] == "ui-change"
        assert any("files:ui" in s for s in result["signals"])

    def test_security_from_prompt(self):
        """Prompt with 'CVE' classifies as security."""
        result = classify_task_type("scan for CVEs")
        assert result["task_type"] == "security"
        assert result["routing"]["gate"] == "hard"

    def test_docs_from_prompt(self):
        """Prompt with 'README' classifies as docs."""
        result = classify_task_type("update the README")
        assert result["task_type"] == "docs"

    def test_refactor_from_prompt(self):
        """Prompt with 'refactor' classifies as refactor."""
        result = classify_task_type("refactor the auth module")
        assert result["task_type"] == "refactor"

    def test_migration_from_prompt(self):
        """Prompt with 'migrate' classifies as migration."""
        result = classify_task_type("migrate from PostgreSQL to MySQL")
        assert result["task_type"] == "migration"

    def test_feature_default(self):
        """Prompt with no specific signals classifies as feature."""
        result = classify_task_type("build a new payment system")
        assert result["task_type"] == "feature"
        assert any("default:feature" in s for s in result["signals"])

    def test_returns_routing_config(self):
        """Result includes routing config dict."""
        result = classify_task_type("fix bug")
        assert "routing" in result
        assert "primary" in result["routing"]
        assert "fallback" in result["routing"]
        assert "strategy" in result["routing"]

    def test_returns_signals_list(self):
        """Result includes signals list."""
        result = classify_task_type("fix security vulnerability")
        assert "signals" in result
        assert isinstance(result["signals"], list)
        assert len(result["signals"]) > 0

    def test_conflicting_signals_picks_strongest(self):
        """When signals conflict, higher-weight signal wins."""
        # Security keywords have higher weight than bugfix
        result = classify_task_type("fix the security vulnerability in auth")
        # Security has weight 2.0 per keyword, and "security" + "vulnerability" + "auth" = 6.0
        # bugfix "fix" = 2.0
        assert result["task_type"] == "security"

    def test_bugfix_beats_feature_on_keyword(self):
        """Bugfix keyword beats feature default."""
        result = classify_task_type("fix the payment processing error")
        assert result["task_type"] == "bugfix"
        assert result["confidence"] > 0.5  # Should have decent confidence

    def test_ui_change_with_css_file(self):
        """CSS files boost ui-change classification."""
        result = classify_task_type("update styles", files=["src/styles.css"])
        assert result["task_type"] == "ui-change"

    def test_migration_from_dockerfile(self):
        """Dockerfile in files boosts migration classification."""
        result = classify_task_type("upgrade container", files=["Dockerfile", "docker-compose.yml"])
        assert result["task_type"] == "migration"

    def test_multiple_ui_files_increase_confidence(self):
        """Multiple UI files increase confidence."""
        result_single = classify_task_type("change", files=["App.tsx"])
        result_multiple = classify_task_type("change", files=["App.tsx", "Button.tsx", "styles.css"])
        assert result_multiple["confidence"] >= result_single["confidence"]


# =============================================================================
# get_routing_for_task Tests
# =============================================================================


class TestGetRoutingForTask:
    """Tests for get_routing_for_task() function."""

    def test_feature_routing(self):
        """Feature task type returns correct routing."""
        routing = get_routing_for_task("feature")
        assert routing["primary"] == "claude"
        assert routing["fallback"] == "codex"
        assert routing["strategy"] == "ccg"
        assert routing["gate"] is None

    def test_bugfix_routing(self):
        """Bugfix task type returns correct routing."""
        routing = get_routing_for_task("bugfix")
        assert routing["primary"] == "codex"
        assert routing["fallback"] == "claude"
        assert routing["strategy"] == "single"

    def test_security_routing(self):
        """Security task type returns correct routing with hard gate."""
        routing = get_routing_for_task("security")
        assert routing["primary"] == "codex"
        assert routing["fallback"] == "claude"
        assert routing["strategy"] == "single"
        assert routing["gate"] == "hard"

    def test_ui_change_routing(self):
        """UI-change task type returns correct routing."""
        routing = get_routing_for_task("ui-change")
        assert routing["primary"] == "gemini"
        assert routing["fallback"] == "claude"
        assert routing["strategy"] == "single"

    def test_refactor_routing(self):
        """Refactor task type returns correct routing."""
        routing = get_routing_for_task("refactor")
        assert routing["primary"] == "claude"
        assert routing["fallback"] == "codex"
        assert routing["strategy"] == "review"

    def test_docs_routing(self):
        """Docs task type returns correct routing with no fallback."""
        routing = get_routing_for_task("docs")
        assert routing["primary"] == "claude"
        assert routing["fallback"] is None
        assert routing["strategy"] == "direct"

    def test_migration_routing(self):
        """Migration task type returns correct routing."""
        routing = get_routing_for_task("migration")
        assert routing["primary"] == "claude"
        assert routing["fallback"] == "codex"
        assert routing["strategy"] == "review"

    def test_unknown_task_type_returns_feature_default(self):
        """Unknown task type returns feature routing as default."""
        routing = get_routing_for_task("unknown-type")
        assert routing["primary"] == "claude"
        assert routing["fallback"] == "codex"
        assert routing["strategy"] == "ccg"
        assert routing["gate"] is None


# =============================================================================
# Edge Cases and Integration
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_empty_prompt(self):
        """Empty prompt defaults to feature."""
        result = classify_task_type("")
        assert result["task_type"] == "feature"

    def test_none_files(self):
        """None files list is handled gracefully."""
        result = classify_task_type("fix bug", files=None)
        assert result["task_type"] == "bugfix"

    def test_empty_files_list(self):
        """Empty files list is handled gracefully."""
        result = classify_task_type("fix bug", files=[])
        assert result["task_type"] == "bugfix"

    def test_case_insensitive_keywords(self):
        """Keywords are matched case-insensitively."""
        result = classify_task_type("FIX THE BUG")
        assert result["task_type"] == "bugfix"

    def test_keyword_in_context(self):
        """Keywords work in longer context."""
        result = classify_task_type("The user reported that the authentication system has a security vulnerability that needs immediate attention")
        assert result["task_type"] == "security"

    def test_clean_up_as_refactor(self):
        """'clean up' phrase classifies as refactor."""
        result = classify_task_type("clean up the legacy code")
        assert result["task_type"] == "refactor"

    def test_dark_mode_as_ui_change(self):
        """'dark mode' phrase classifies as ui-change."""
        result = classify_task_type("implement dark mode for the app")
        assert result["task_type"] == "ui-change"
