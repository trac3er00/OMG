"""Integration tests for MCP config hardening defaults."""
import json
import os
import sys

WORKTREE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "hooks"))


def test_mcp_json_filesystem_scopes_to_project_root():
    """Filesystem MCP should be scoped to the current project, not $HOME."""
    mcp_path = os.path.join(WORKTREE_ROOT, ".mcp.json")
    with open(mcp_path) as f:
        cfg = json.load(f)
    args = cfg["mcpServers"]["filesystem"]["args"]
    assert args[-1] == ".", f"Expected project root '.', got {args[-1]}"


def test_mcp_json_pins_versions_without_auto_install_flags():
    mcp_path = os.path.join(WORKTREE_ROOT, ".mcp.json")
    with open(mcp_path) as f:
        cfg = json.load(f)

    for server in cfg["mcpServers"].values():
        if server.get("command") != "npx":
            continue
        args = server.get("args", [])
        assert "-y" not in args
        assert "--yes" not in args
        for arg in args:
            if isinstance(arg, str) and "chrome-devtools-mcp" in arg:
                assert "@latest" not in arg


def test_mcp_json_has_five_servers():
    mcp_path = os.path.join(WORKTREE_ROOT, ".mcp.json")
    with open(mcp_path) as f:
        cfg = json.load(f)
    assert len(cfg["mcpServers"]) == 5


def test_build_mcp_config_filesystem_scopes_to_project_root():
    from setup_wizard import build_mcp_config

    cfg = build_mcp_config(["filesystem"])
    args = cfg["mcpServers"]["filesystem"]["args"]
    assert args[-1] == ".", f"Expected project root '.', got {args[-1]}"
