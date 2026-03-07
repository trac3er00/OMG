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
