from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_claude_plugin_manifest_exists_and_points_to_mcp_config():
    manifest_path = ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "omg"
    assert manifest["mcpServers"] == "./.mcp.json"


def test_plugin_mcp_config_includes_required_servers():
    mcp_path = ROOT / ".mcp.json"
    assert mcp_path.exists()

    mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    servers = mcp.get("mcpServers", {})
    assert "context7" in servers
    assert "filesystem" in servers
    assert "websearch" in servers
    assert "chrome-devtools" in servers


def test_plugin_manifest_mcp_servers_reference_exists():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict), "plugin.json must be a JSON object"
    if "mcpServers" in manifest:
        mcp_ref = manifest["mcpServers"]
        if isinstance(mcp_ref, str):
            assert (ROOT / ".mcp.json").exists(), f"mcpServers path reference {mcp_ref!r} target missing"
        else:
            assert isinstance(mcp_ref, dict), "mcpServers must be a string path or dict"


def test_plugin_command_manifests_use_plain_source_paths():
    for manifest_relpath in ("plugins/core/plugin.json", "plugins/advanced/plugin.json"):
        manifest_path = ROOT / manifest_relpath
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for command in manifest["commands"].values():
            path = command["path"]
            assert "OMG:" not in path
            resolved = manifest_path.parent / path
            if not resolved.exists():
                resolved = ROOT / path
            assert resolved.exists()
