#!/usr/bin/env python3
"""Tests for MCP duplicate detection in session-start hook.

Tests the production functions from runtime.mcp_utils to ensure
duplicate MCP server detection works correctly.
"""
from __future__ import annotations

import pytest

# Import production functions - tests validate the real implementation
from runtime.mcp_utils import (
    extract_mcp_base_name as _extract_mcp_base_name,
    detect_duplicate_mcp_servers as _detect_duplicate_mcp_servers,
)


class TestMCPBaseNameExtraction:
    """Test MCP server base name extraction logic."""

    def test_plugin_linear_linear(self):
        assert _extract_mcp_base_name("plugin_linear_linear") == "linear"

    def test_claude_ai_linear(self):
        assert _extract_mcp_base_name("claude_ai_Linear") == "linear"

    def test_plugin_omg_omg_control(self):
        assert _extract_mcp_base_name("plugin_omg_omg-control") == "omg-control"

    def test_omg_control(self):
        assert _extract_mcp_base_name("omg-control") == "omg-control"

    def test_filesystem(self):
        assert _extract_mcp_base_name("filesystem") == "filesystem"

    def test_claude_ai_slack(self):
        assert _extract_mcp_base_name("claude_ai_Slack") == "slack"

    def test_mcp_prefix(self):
        assert _extract_mcp_base_name("mcp_github") == "github"


class TestMCPDuplicateDetection:
    """Test MCP duplicate server detection."""

    def test_linear_duplicates(self):
        """Test detection of Linear duplicate servers from user's issue."""
        servers = {
            "plugin_linear_linear": {},
            "claude_ai_Linear": {},
            "filesystem": {},
        }
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 1
        assert "linear" in warnings[0].lower()
        assert "plugin_linear_linear" in warnings[0]
        assert "claude_ai_Linear" in warnings[0]

    def test_omg_control_duplicates(self):
        """Test detection of omg-control duplicate servers."""
        servers = {
            "plugin_omg_omg-control": {},
            "omg-control": {},
        }
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 1
        assert "omg-control" in warnings[0].lower()
        assert "plugin_omg_omg-control" in warnings[0]
        assert "omg-control" in warnings[0]

    def test_multiple_duplicate_groups(self):
        """Test detection of multiple groups of duplicates."""
        servers = {
            "plugin_linear_linear": {},
            "claude_ai_Linear": {},
            "plugin_omg_omg-control": {},
            "omg-control": {},
            "filesystem": {},
        }
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 2
        # Check that both groups are detected
        warning_text = "\n".join(warnings)
        assert "linear" in warning_text.lower()
        assert "omg-control" in warning_text.lower()

    def test_no_duplicates(self):
        """Test no warnings when no duplicates exist."""
        servers = {
            "filesystem": {},
            "claude_ai_Slack": {},
            "github": {},
        }
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 0

    def test_empty_servers(self):
        """Test empty server list."""
        servers = {}
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 0

    def test_sorted_output(self):
        """Test that duplicate names are sorted in output."""
        servers = {
            "plugin_slack_slack": {},
            "claude_ai_Slack": {},
        }
        # Both should normalize to "slack"
        warnings = _detect_duplicate_mcp_servers(servers)
        assert len(warnings) == 1
        # Should be sorted: claude_ai_Slack, plugin_slack_slack
        assert warnings[0].index("claude_ai_Slack") < warnings[0].index("plugin_slack_slack")

    def test_real_world_scenario(self):
        """Test with the exact scenario from user's issue."""
        servers = {
            "claude_ai_Slack": {},
            "plugin_linear_linear": {},
            "claude_ai_Linear": {},
            "filesystem": {},
            "plugin_omg_omg-control": {},
            "omg-control": {},
        }
        warnings = _detect_duplicate_mcp_servers(servers)
        # Should detect 2 duplicate groups: linear and omg-control
        assert len(warnings) == 2
        warning_text = "\n".join(warnings)
        assert "linear" in warning_text.lower()
        assert "omg-control" in warning_text.lower()
        # Slack and filesystem should not be flagged
        assert "slack" not in warning_text.lower() or "duplicate" not in warning_text.lower()
        assert "filesystem" not in warning_text.lower() or "duplicate" not in warning_text.lower()
