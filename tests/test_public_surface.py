from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_readme_and_docs_promote_security_check_not_security_review():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    proof = (ROOT / "docs" / "proof.md").read_text(encoding="utf-8")

    assert "/OMG:security-check" in readme
    assert "/OMG:security-review" not in readme
    assert "/OMG:security-review" not in plugins_readme
    assert "/OMG:security-review" not in proof


def test_core_plugin_manifest_includes_new_canonical_surfaces():
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text(encoding="utf-8"))
    commands = manifest["commands"]

    assert "security-check" in commands
    assert "api-twin" in commands
    assert "preflight" in commands


def test_advanced_plugin_manifest_no_longer_markets_security_review():
    manifest = json.loads((ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8"))
    assert "security-review" not in manifest["commands"]


def test_advanced_plugin_command_paths_resolve_relative_to_plugin_root():
    """Verify all command paths in advanced plugin resolve relative to plugins/advanced/"""
    manifest = json.loads((ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8"))
    plugin_root = ROOT / "plugins" / "advanced"
    
    for cmd_name, cmd_config in manifest["commands"].items():
        path = cmd_config["path"]
        resolved = plugin_root / path
        assert resolved.exists(), f"Command '{cmd_name}' path '{path}' does not resolve to {resolved}"


def test_security_auditor_uses_canonical_security_check():
    """Verify omg-security-auditor.md no longer references deprecated /OMG:security-review"""
    auditor = (ROOT / "agents" / "omg-security-auditor.md").read_text(encoding="utf-8")
    assert "/OMG:security-review" not in auditor
    assert "/OMG:security-check" in auditor
