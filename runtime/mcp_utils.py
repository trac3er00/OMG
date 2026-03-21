"""MCP utility functions for server name normalization and duplicate detection."""
from __future__ import annotations

from collections import defaultdict


def extract_mcp_base_name(server_name: str) -> str:
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
            name = name[len(prefix) :]
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


def detect_duplicate_mcp_servers(all_servers: dict[str, dict]) -> list[str]:
    """Detect duplicate MCP servers with similar names.

    Returns list of warning messages about detected duplicates.
    """
    # Group servers by base name
    groups: dict[str, list[str]] = defaultdict(list)
    for server_name, _server_config in all_servers.items():
        base_name = extract_mcp_base_name(server_name)
        groups[base_name].append(server_name)

    # Find groups with duplicates
    warnings = []
    for base_name, server_names in groups.items():
        if len(server_names) >= 2:
            # Sort to ensure consistent output
            sorted_names = sorted(server_names)
            warnings.append(
                f"  \u26a0 Duplicate MCP servers detected for '{base_name}': {', '.join(sorted_names)}"
            )

    return warnings
