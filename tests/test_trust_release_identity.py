"""Trust-release identity drift checks."""
from __future__ import annotations

import json
from pathlib import Path

from runtime.adoption import CANONICAL_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_trust_release_identity_is_canonical():
    package = _load_json(ROOT / "package.json")
    settings = _load_json(ROOT / "settings.json")
    plugin = _load_json(ROOT / ".claude-plugin" / "plugin.json")
    marketplace = _load_json(ROOT / ".claude-plugin" / "marketplace.json")
    core_plugin = _load_json(ROOT / "plugins" / "core" / "plugin.json")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert package["name"] == "@trac3er/oh-my-god"
    assert package["version"] == CANONICAL_VERSION
    assert package["repository"] == {
        "type": "git",
        "url": "git+https://github.com/trac3er00/OMG.git",
    }
    assert package["homepage"] == "https://github.com/trac3er00/OMG#readme"

    omg_settings = settings["_omg"]
    assert omg_settings["_version"] == CANONICAL_VERSION
    assert omg_settings["preset"] == "safe"

    assert plugin["name"] == "omg"
    assert plugin["version"] == CANONICAL_VERSION
    assert plugin["repository"] == "https://github.com/trac3er00/OMG"

    assert marketplace["name"] == "omg"
    assert marketplace["version"] == CANONICAL_VERSION
    assert marketplace["metadata"]["version"] == CANONICAL_VERSION
    assert marketplace["metadata"]["repository"] == "https://github.com/trac3er00/OMG"

    plugins = marketplace["plugins"]
    assert isinstance(plugins, list)
    assert plugins[0]["name"] == "omg"
    assert plugins[0]["version"] == CANONICAL_VERSION

    assert core_plugin["version"] == CANONICAL_VERSION
    assert "setup" in core_plugin["commands"]
    assert "compat" in core_plugin["commands"]

    assert readme.startswith("# OMG")
    assert "https://github.com/trac3er00/OMG" in readme
    assert "@trac3er/oh-my-god" in readme
