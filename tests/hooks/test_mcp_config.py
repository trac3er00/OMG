"""Integration tests for MCP config and settings template."""
import json
import os
import sys

import pytest

WORKTREE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "hooks"))


def test_mcp_json_filesystem_uses_home_dir():
    """Filesystem MCP should use $HOME not '.'."""
    mcp_path = os.path.join(WORKTREE_ROOT, ".mcp.json")
    with open(mcp_path) as f:
        cfg = json.load(f)
    args = cfg["mcpServers"]["filesystem"]["args"]
    home = os.path.expanduser("~")
    assert args[-1] == home, f"Expected {home}, got {args[-1]}"


def test_mcp_json_has_five_servers():
    mcp_path = os.path.join(WORKTREE_ROOT, ".mcp.json")
    with open(mcp_path) as f:
        cfg = json.load(f)
    assert len(cfg["mcpServers"]) == 5


def test_settings_has_plan_type():
    settings_path = os.path.join(WORKTREE_ROOT, "settings.json")
    with open(settings_path) as f:
        s = json.load(f)
    assert "plan_type" in s["_omg"]
    assert s["_omg"]["plan_type"] == "max"


def test_settings_has_model_routing():
    settings_path = os.path.join(WORKTREE_ROOT, "settings.json")
    with open(settings_path) as f:
        s = json.load(f)
    assert "model_routing" in s["_omg"]
    mr = s["_omg"]["model_routing"]
    assert "planning" in mr
    assert "coding" in mr


def test_settings_has_bypass_all():
    settings_path = os.path.join(WORKTREE_ROOT, "settings.json")
    with open(settings_path) as f:
        s = json.load(f)
    assert "bypass_all" in s["_omg"]
    assert s["_omg"]["bypass_all"] is False


def test_settings_has_setup_in_progress():
    settings_path = os.path.join(WORKTREE_ROOT, "settings.json")
    with open(settings_path) as f:
        s = json.load(f)
    assert "setup_in_progress" in s["_omg"]
    assert s["_omg"]["setup_in_progress"] is False


def test_build_mcp_config_filesystem_uses_home():
    from setup_wizard import build_mcp_config

    cfg = build_mcp_config(["filesystem"])
    home = os.path.expanduser("~")
    args = cfg["mcpServers"]["filesystem"]["args"]
    assert args[-1] == home, f"Expected {home}, got {args[-1]}"
