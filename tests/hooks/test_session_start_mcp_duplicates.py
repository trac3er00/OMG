#!/usr/bin/env python3
"""Tests for MCP duplicate detection in session-start hook."""
from __future__ import annotations

import pytest


def _extract_mcp_base_name(server_name: str) -> str:
    """Extract base name from MCP server name.

    Examples:
        plugin_linear_linear -> linear
        claude_ai_Linear -> linear
        plugin_omg_omg-control -> omg-control
        omg-control -> omg-control
        filesystem -> filesystem
    """
    # Remove common prefixes
    name = server_name
    for prefix in ["plugin_", "claude_ai_", "mcp_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    # Handle cases like "plugin_linear_linear" -> "linear_linear" -> "linear"
    # Check if we have a pattern like "X_X" or "X_X-Y"
    parts = name.split("_")
    if len(parts) >= 2:
        # Case 1: exact duplicate like "linear_linear"
        if parts[-1] == parts[-2]:
            return parts[-1].lower()
        # Case 2: pattern like "omg_omg-control" where first part matches start of second
        if len(parts) == 2 and parts[1].startswith(parts[0]):
            # Take the longer, more specific part
            return parts[1].lower()

    return name.lower()


def _detect_duplicate_mcp_servers(all_servers: dict[str, dict]) -> list[str]:
    """Detect duplicate MCP servers with similar names.

    Returns list of warning messages about detected duplicates.
    """
    from collections import defaultdict

    # Group servers by base name
    groups = defaultdict(list)
    for server_name, server_config in all_servers.items():
        base_name = _extract_mcp_base_name(server_name)
        groups[base_name].append(server_name)

    # Find groups with duplicates
    warnings = []
    for base_name, server_names in groups.items():
        if len(server_names) >= 2:
            # Sort to ensure consistent output
            sorted_names = sorted(server_names)
            warnings.append(
                f"  ⚠ Duplicate MCP servers detected for '{base_name}': {', '.join(sorted_names)}"
            )

    return warnings


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
