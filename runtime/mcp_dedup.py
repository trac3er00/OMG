"""MCP Overlap Detection — scan for duplicate MCP server configurations.

Scans user-level (~/.claude/.mcp.json) and project-level (.mcp.json) for
overlapping MCP server registrations and reports conflicts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def scan_mcp_configs(project_dir: str) -> dict[str, Any]:
    """Scan all .mcp.json files and detect overlaps.

    Returns:
        {
            "configs": [{path, servers: [...]}],
            "overlaps": [{server_name, locations: [...], severity}],
            "capability_map": {server_name: [capabilities]},
        }
    """
    configs: list[dict[str, Any]] = []
    server_locations: dict[str, list[str]] = {}

    # User-level
    user_mcp = os.path.expanduser("~/.claude/.mcp.json")
    _scan_file(user_mcp, "user", configs, server_locations)

    # Project-level
    project_mcp = os.path.join(project_dir, ".mcp.json")
    _scan_file(project_mcp, "project", configs, server_locations)

    # Detect overlaps
    overlaps: list[dict[str, Any]] = []
    for server_name, locations in server_locations.items():
        if len(locations) > 1:
            same_level = len(set(loc.split(":")[0] for loc in locations)) == 1
            overlaps.append({
                "server_name": server_name,
                "locations": locations,
                "severity": "info" if same_level else "warning",
                "same_level": same_level,
            })

    # Capability map (known OMG MCPs)
    capability_map = _build_capability_map(server_locations)

    return {
        "configs": configs,
        "overlaps": overlaps,
        "capability_map": capability_map,
        "has_duplicates": len(overlaps) > 0,
    }


def _scan_file(
    path: str,
    level: str,
    configs: list[dict[str, Any]],
    server_locations: dict[str, list[str]],
) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    servers = []
    mcp_servers = data.get("mcpServers", {})
    if isinstance(mcp_servers, dict):
        for name in mcp_servers:
            servers.append(name)
            locations = server_locations.setdefault(name, [])
            locations.append(f"{level}:{path}")

    configs.append({"path": path, "level": level, "servers": servers})


KNOWN_CAPABILITIES: dict[str, list[str]] = {
    "omg-control": ["policy", "governance", "claim-judge", "evidence"],
    "omg-memory": ["memory", "state", "persistence"],
    "context7": ["documentation", "library-docs", "code-examples"],
    "filesystem": ["file-read", "file-write", "directory-list"],
    "websearch": ["web-search", "url-fetch"],
    "chrome-devtools": ["browser", "screenshot", "dom-inspect"],
    "grep-app": ["code-search", "regex"],
}


def _build_capability_map(server_locations: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for server_name in server_locations:
        result[server_name] = KNOWN_CAPABILITIES.get(server_name, ["unknown"])
    return result


def format_overlap_report(scan_result: dict[str, Any]) -> str:
    """Format a human-readable overlap report."""
    lines = ["MCP Overlap Detection Report", "=" * 40]

    for config in scan_result["configs"]:
        lines.append(f"\n[{config['level']}] {config['path']}")
        for s in config["servers"]:
            lines.append(f"  - {s}")

    if scan_result["overlaps"]:
        lines.append(f"\nOverlaps Found: {len(scan_result['overlaps'])}")
        for overlap in scan_result["overlaps"]:
            sev = overlap["severity"].upper()
            lines.append(f"  [{sev}] {overlap['server_name']}")
            for loc in overlap["locations"]:
                lines.append(f"    - {loc}")
            if overlap["same_level"]:
                lines.append("    Action: Remove duplicate (same level)")
            else:
                lines.append("    Action: Review — different levels may be intentional")
    else:
        lines.append("\nNo overlaps detected.")

    return "\n".join(lines)
