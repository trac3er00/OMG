"""Trust-release identity drift checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.adoption import CANONICAL_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_trust_release_identity_is_canonical():
    package = _load_json(ROOT / "package.json")
    settings = _load_json(ROOT / "settings.json")
    plugin = _load_json(ROOT / ".claude-plugin" / "plugin.json")
    marketplace = _load_json(ROOT / ".claude-plugin" / "marketplace.json")
    core_plugin = _load_json(ROOT / "plugins" / "core" / "plugin.json")
    dist_public = _load_json(ROOT / "dist" / "public" / "manifest.json")
    dist_enterprise = _load_json(ROOT / "dist" / "enterprise" / "manifest.json")
    release_public = _load_json(ROOT / "artifacts" / "release" / "dist" / "public" / "manifest.json")
    release_enterprise = _load_json(ROOT / "artifacts" / "release" / "dist" / "enterprise" / "manifest.json")
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
    assert "plan-council" in core_plugin["roles"]

    for manifest in (dist_public, dist_enterprise, release_public, release_enterprise):
        assert manifest["schema"] == "OmgCompiledArtifactManifest"
        assert manifest["contract_version"] == CANONICAL_VERSION

    assert readme.startswith("# OMG")
    assert "https://github.com/trac3er00/OMG" in readme
    assert "@trac3er/oh-my-god" in readme


def test_runtime_consumer_surfaces_match_canonical():
    setup_sh = (ROOT / "OMG-setup.sh").read_text(encoding="utf-8")
    hud_mjs = (ROOT / "hud" / "omg-hud.mjs").read_text(encoding="utf-8")

    assert f'VERSION="{CANONICAL_VERSION}"' in setup_sh, (
        f"OMG-setup.sh VERSION must be {CANONICAL_VERSION}"
    )
    assert f'return "{CANONICAL_VERSION}"' in hud_mjs, (
        f"hud/omg-hud.mjs static fallback must be {CANONICAL_VERSION}"
    )


def test_runtime_consumer_install_sh_version():
    content = (ROOT / ".claude-plugin" / "scripts" / "install.sh").read_text(
        encoding="utf-8"
    )
    assert f"v{CANONICAL_VERSION}" in content, (
        f"install.sh banner must reference v{CANONICAL_VERSION}"
    )


@pytest.mark.xfail(
    reason="stale version 2.1.0 in frontmatter — needs sync-release-identity",
    strict=True,
)
def test_generated_release_artifacts_match_canonical():
    content = (
        ROOT / "artifacts" / "release" / "OMG_COMPAT_CONTRACT.md"
    ).read_text(encoding="utf-8")
    assert f"version: {CANONICAL_VERSION}" in content, (
        f"OMG_COMPAT_CONTRACT.md frontmatter must have version: {CANONICAL_VERSION}"
    )


@pytest.mark.xfail(
    reason="stale version 2.1.0 — needs sync-release-identity (pytest-only check)",
    strict=True,
)
def test_cli_adapter_map_version_examples():
    content = (ROOT / "CLI-ADAPTER-MAP.md").read_text(encoding="utf-8")
    assert f"**Version:** `{CANONICAL_VERSION}`" in content, (
        f"CLI-ADAPTER-MAP.md version example must be {CANONICAL_VERSION}"
    )
