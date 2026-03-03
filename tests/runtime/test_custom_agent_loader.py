"""Tests for custom agent loader (Task 2.4)."""
from __future__ import annotations

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock, call

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOOKS_DIR = os.path.join(_ROOT, "hooks")
_RUNTIME_DIR = os.path.join(_ROOT, "runtime")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)

from runtime.custom_agent_loader import (
    _validate_agent_schema,
    _extract_agent_name,
    _extract_description,
    _extract_model_role,
    _is_enabled,
    _scan_agents_dir,
    load_custom_agents,
    get_all_agents,
    watch_for_changes,
    _get_dir_state,
)


# --- Fixtures ---

VALID_AGENT_MD = """\
---
name: test-agent
description: A test agent
model: claude-sonnet-4-5
---

# Agent: Test Agent

## Role

A test agent for validating the custom agent loader framework.

## Model

`default` (claude-sonnet-4-5) — general-purpose model.

## Capabilities

- Test capability 1
- Test capability 2

## Instructions

Follow the test instructions carefully.
"""

MINIMAL_VALID_AGENT_MD = """\
# Agent: Minimal

## Role

A minimal valid agent with only required sections.
"""

MISSING_HEADER_MD = """\
## Role

An agent without the required header.
"""

MISSING_ROLE_MD = """\
# Agent: NoRole

## Model

`default` — missing role section.
"""

EMPTY_CONTENT = ""

WHITESPACE_ONLY = "   \n\n  \t  "


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestValidateAgentSchema:
    """Tests for _validate_agent_schema()."""

    def test_valid_full_agent(self):
        """Full agent with all sections passes validation."""
        is_valid, issues = _validate_agent_schema(VALID_AGENT_MD)
        assert is_valid is True
        assert issues == []

    def test_valid_minimal_agent(self):
        """Minimal agent with only required sections passes."""
        is_valid, issues = _validate_agent_schema(MINIMAL_VALID_AGENT_MD)
        assert is_valid is True
        assert issues == []

    def test_missing_header_fails(self):
        """Agent without # Agent: header fails validation."""
        is_valid, issues = _validate_agent_schema(MISSING_HEADER_MD)
        assert is_valid is False
        assert any("Agent:" in issue for issue in issues)

    def test_missing_role_fails(self):
        """Agent without ## Role section fails validation."""
        is_valid, issues = _validate_agent_schema(MISSING_ROLE_MD)
        assert is_valid is False
        assert any("Role" in issue for issue in issues)

    def test_both_missing_fails(self):
        """Agent missing both header and role fails with 2 issues."""
        is_valid, issues = _validate_agent_schema("Some random text")
        assert is_valid is False
        assert len(issues) == 2

    def test_empty_content_fails(self):
        """Empty content fails validation."""
        is_valid, issues = _validate_agent_schema(EMPTY_CONTENT)
        assert is_valid is False
        assert any("empty" in issue.lower() for issue in issues)

    def test_whitespace_only_fails(self):
        """Whitespace-only content fails validation."""
        is_valid, issues = _validate_agent_schema(WHITESPACE_ONLY)
        assert is_valid is False


# =============================================================================
# Name/Description/Role Extraction Tests
# =============================================================================


class TestExtraction:
    """Tests for _extract_agent_name, _extract_description, _extract_model_role."""

    def test_extract_name_from_header(self):
        """Extracts name from # Agent: header."""
        name = _extract_agent_name(VALID_AGENT_MD, "test-agent.md")
        assert name == "test_agent"

    def test_extract_name_fallback_to_filename(self):
        """Falls back to filename when header has no name."""
        name = _extract_agent_name("# Some other heading\n## Role\nText", "my-agent.md")
        assert name == "my_agent"

    def test_extract_description_from_role(self):
        """Extracts first line of ## Role section as description."""
        desc = _extract_description(VALID_AGENT_MD)
        assert "test agent" in desc.lower()

    def test_extract_description_empty_when_no_role(self):
        """Returns empty string when no Role section."""
        desc = _extract_description("# Agent: Test\n\nNo role section.")
        assert desc == ""

    def test_extract_model_role_default(self):
        """Extracts 'default' from Model section."""
        role = _extract_model_role(VALID_AGENT_MD)
        assert role == "default"

    def test_extract_model_role_smol(self):
        """Extracts 'smol' from Model section."""
        content = "# Agent: Fast\n\n## Role\nFast agent.\n\n## Model\n`smol` (haiku)\n"
        role = _extract_model_role(content)
        assert role == "smol"

    def test_extract_model_role_none_when_missing(self):
        """Returns None when no Model section."""
        role = _extract_model_role(MINIMAL_VALID_AGENT_MD)
        assert role is None


# =============================================================================
# Feature Flag Tests
# =============================================================================


class TestFeatureFlag:
    """Tests for feature flag behavior."""

    def test_disabled_returns_empty_list(self):
        """load_custom_agents returns empty list when feature disabled."""
        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "0"}, clear=False):
            result = load_custom_agents(".")
            assert result == []

    def test_enabled_via_env(self):
        """_is_enabled returns True when env var is set to '1'."""
        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            assert _is_enabled() is True

    def test_disabled_via_env_false(self):
        """_is_enabled returns False when env var is 'false'."""
        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "false"}, clear=False):
            assert _is_enabled() is False

    def test_disabled_by_default(self):
        """_is_enabled returns False when env var not set (default)."""
        env = os.environ.copy()
        env.pop("OAL_CUSTOM_AGENTS_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            # Mock get_feature_flag to return False (default)
            with patch("runtime.custom_agent_loader._get_feature_flag") as mock_flag:
                mock_fn = MagicMock(return_value=False)
                mock_flag.return_value = mock_fn
                assert _is_enabled() is False


# =============================================================================
# Directory Scanning Tests
# =============================================================================


class TestScanAgentsDir:
    """Tests for _scan_agents_dir and directory scanning."""

    def test_scan_nonexistent_dir(self):
        """Returns empty list for nonexistent directory."""
        agents = _scan_agents_dir("/nonexistent/path/agents", "user")
        assert agents == []

    def test_scan_with_valid_agent(self, tmp_path):
        """Finds and validates a valid agent file."""
        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text(VALID_AGENT_MD)

        agents = _scan_agents_dir(str(tmp_path), "project")
        assert len(agents) == 1
        assert agents[0]["name"] == "test_agent"
        assert agents[0]["validated"] is True
        assert agents[0]["level"] == "project"

    def test_scan_with_invalid_agent(self, tmp_path):
        """Finds but marks invalid agent as not validated."""
        agent_file = tmp_path / "bad-agent.md"
        agent_file.write_text(MISSING_ROLE_MD)

        agents = _scan_agents_dir(str(tmp_path), "user")
        assert len(agents) == 1
        assert agents[0]["validated"] is False
        assert len(agents[0]["issues"]) > 0

    def test_scan_ignores_non_md_files(self, tmp_path):
        """Ignores non-.md files."""
        (tmp_path / "readme.txt").write_text("Not an agent")
        (tmp_path / "agent.md").write_text(MINIMAL_VALID_AGENT_MD)

        agents = _scan_agents_dir(str(tmp_path), "project")
        assert len(agents) == 1

    def test_scan_multiple_agents(self, tmp_path):
        """Scans multiple agent files correctly."""
        (tmp_path / "agent-a.md").write_text(MINIMAL_VALID_AGENT_MD)
        (tmp_path / "agent-b.md").write_text(VALID_AGENT_MD)

        agents = _scan_agents_dir(str(tmp_path), "project")
        assert len(agents) == 2


# =============================================================================
# Project Override Tests
# =============================================================================


class TestProjectOverride:
    """Tests for project-level overriding user-level agents."""

    def test_project_overrides_user(self, tmp_path):
        """Project-level agent overrides user-level agent with same name."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project"
        project_agents = project_dir / ".oal" / "agents"
        project_agents.mkdir(parents=True)

        # User agent
        (user_dir / "shared.md").write_text(
            "# Agent: Shared\n\n## Role\n\nUser-level shared agent.\n"
        )
        # Project agent (same name)
        (project_agents / "shared.md").write_text(
            "# Agent: Shared\n\n## Role\n\nProject-level shared agent.\n"
        )

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(user_dir)):
                agents = load_custom_agents(str(project_dir))

        # Should have 1 agent (project overrides user)
        assert len(agents) == 1
        assert agents[0]["level"] == "project"
        assert "Project-level" in agents[0]["description"]

    def test_user_only_when_no_project(self, tmp_path):
        """Returns user agents when no project agents dir exists."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        (user_dir / "my-agent.md").write_text(MINIMAL_VALID_AGENT_MD)

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(user_dir)):
                agents = load_custom_agents(str(project_dir))

        assert len(agents) == 1
        assert agents[0]["level"] == "user"


# =============================================================================
# get_all_agents Merge Tests
# =============================================================================


class TestGetAllAgents:
    """Tests for get_all_agents() merging built-in + custom."""

    def test_includes_builtin_agents(self):
        """Built-in agents are present in merged result."""
        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "0"}, clear=False):
            result = get_all_agents(".")
            # Should have built-in agents
            assert "explore" in result
            assert "plan" in result
            assert result["explore"].get("source") == "builtin"

    def test_custom_agent_overrides_builtin(self, tmp_path):
        """Custom agent with same name overrides built-in."""
        project_agents = tmp_path / ".oal" / "agents"
        project_agents.mkdir(parents=True)
        (project_agents / "explore.md").write_text(
            "# Agent: Explore\n\n## Role\n\nCustom explore agent.\n"
        )

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                result = get_all_agents(str(tmp_path))

        assert result["explore"]["source"] == "custom"
        assert "Custom explore" in result["explore"]["description"]

    def test_custom_agents_added_alongside_builtin(self, tmp_path):
        """Custom agents are added alongside built-in agents."""
        project_agents = tmp_path / ".oal" / "agents"
        project_agents.mkdir(parents=True)
        (project_agents / "my-custom.md").write_text(
            "# Agent: My Custom\n\n## Role\n\nA brand new custom agent.\n"
        )

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                result = get_all_agents(str(tmp_path))

        assert "my_custom" in result
        assert "explore" in result  # Built-in still present
        assert result["my_custom"]["source"] == "custom"

    def test_invalid_custom_agents_excluded(self, tmp_path):
        """Invalid custom agents are not included in merged result."""
        project_agents = tmp_path / ".oal" / "agents"
        project_agents.mkdir(parents=True)
        (project_agents / "bad.md").write_text(MISSING_ROLE_MD)

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                result = get_all_agents(str(tmp_path))

        assert "norole" not in result  # Invalid agent excluded


# =============================================================================
# Watch for Changes Tests
# =============================================================================


class TestWatchForChanges:
    """Tests for watch_for_changes() polling mechanism."""

    def test_detects_new_file(self, tmp_path):
        """Detects when a new agent file is created."""
        project_dir = tmp_path / "project"
        agents_dir = project_dir / ".oal" / "agents"
        agents_dir.mkdir(parents=True)

        callback = MagicMock()

        # Create file after initial state is captured
        def create_file_after_sleep(*args, **kwargs):
            # Original sleep behavior but also create a file
            (agents_dir / "new-agent.md").write_text(MINIMAL_VALID_AGENT_MD)

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                with patch("time.sleep", side_effect=create_file_after_sleep):
                    watch_for_changes(str(project_dir), callback, poll_interval=0.01, max_iterations=1)

        callback.assert_called_once()

    def test_no_callback_when_no_changes(self, tmp_path):
        """No callback when nothing changes."""
        project_dir = tmp_path / "project"
        agents_dir = project_dir / ".oal" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "stable.md").write_text(MINIMAL_VALID_AGENT_MD)

        callback = MagicMock()

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("runtime.custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                with patch("time.sleep"):
                    watch_for_changes(str(project_dir), callback, poll_interval=0.01, max_iterations=1)

        callback.assert_not_called()


# =============================================================================
# Dir State Tests
# =============================================================================


class TestGetDirState:
    """Tests for _get_dir_state() helper."""

    def test_empty_for_nonexistent_dir(self):
        """Returns empty dict for nonexistent directory."""
        state = _get_dir_state("/nonexistent/path")
        assert state == {}

    def test_returns_mtime_for_md_files(self, tmp_path):
        """Returns mtime for .md files only."""
        (tmp_path / "agent.md").write_text("test")
        (tmp_path / "readme.txt").write_text("test")

        state = _get_dir_state(str(tmp_path))
        assert len(state) == 1
        assert any("agent.md" in k for k in state)


# =============================================================================
# Registry Integration Tests
# =============================================================================


class TestRegistryIntegration:
    """Tests for load_custom_agents_into_registry in _agent_registry.py."""

    def test_disabled_returns_zero(self):
        """Returns 0 when feature disabled."""
        from _agent_registry import load_custom_agents_into_registry
        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "0"}, clear=False):
            count = load_custom_agents_into_registry(".")
            assert count == 0

    def test_loads_valid_agents(self, tmp_path):
        """Loads valid custom agents into AGENT_REGISTRY."""
        from _agent_registry import load_custom_agents_into_registry, AGENT_REGISTRY

        project_agents = tmp_path / ".oal" / "agents"
        project_agents.mkdir(parents=True)
        (project_agents / "custom-test.md").write_text(
            "# Agent: Custom Test\n\n## Role\n\nA test custom agent.\n"
        )

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                count = load_custom_agents_into_registry(str(tmp_path))

        assert count == 1
        assert "custom_test" in AGENT_REGISTRY
        assert AGENT_REGISTRY["custom_test"]["source"] == "custom"

        # Cleanup
        AGENT_REGISTRY.pop("custom_test", None)

    def test_skips_invalid_agents(self, tmp_path):
        """Skips invalid agents (missing required sections)."""
        from _agent_registry import load_custom_agents_into_registry, AGENT_REGISTRY

        project_agents = tmp_path / ".oal" / "agents"
        project_agents.mkdir(parents=True)
        (project_agents / "invalid.md").write_text(MISSING_ROLE_MD)

        original_keys = set(AGENT_REGISTRY.keys())

        with patch.dict(os.environ, {"OAL_CUSTOM_AGENTS_ENABLED": "1"}, clear=False):
            with patch("custom_agent_loader._get_user_agents_dir", return_value=str(tmp_path / "no_user")):
                count = load_custom_agents_into_registry(str(tmp_path))

        assert count == 0
        assert set(AGENT_REGISTRY.keys()) == original_keys


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_agent_header_various_formats(self):
        """Various # Agent: header formats pass validation."""
        for content in [
            "# Agent: Simple\n\n## Role\n\nA role.\n",
            "# Agent: Multi Word Name\n\n## Role\n\nA role.\n",
            "# Agent: agent-with-dashes\n\n## Role\n\nA role.\n",
        ]:
            is_valid, issues = _validate_agent_schema(content)
            assert is_valid is True, f"Failed for: {content[:30]}"

    def test_large_content_truncated(self, tmp_path):
        """Large files are read with size limit."""
        agent_file = tmp_path / "big.md"
        # Write a file that starts valid but is very large
        content = "# Agent: Big\n\n## Role\n\nA role.\n" + ("x" * 300_000)
        agent_file.write_text(content)

        agents = _scan_agents_dir(str(tmp_path), "project")
        assert len(agents) == 1
        assert agents[0]["validated"] is True
