"""Trust-release identity drift checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.adoption import CANONICAL_VERSION
from runtime.release_surfaces import AUTHORED_SURFACES, get_authored_paths

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

    _ATTESTATION_REQUIRED_KEYS = {"artifact_path", "statement_path", "signature_path", "signer_key_id", "algorithm"}
    for manifest in (dist_public, dist_enterprise, release_public, release_enterprise):
        assert manifest["schema"] == "OmgCompiledArtifactManifest"
        assert manifest["contract_version"] == CANONICAL_VERSION
        attestations = manifest.get("attestations")
        assert isinstance(attestations, list), "compiled manifest must include attestations array"
        assert len(attestations) == len(manifest["artifacts"])
        for row in attestations:
            assert _ATTESTATION_REQUIRED_KEYS <= set(row), f"attestation row missing: {_ATTESTATION_REQUIRED_KEYS - set(row)}"
            assert row["algorithm"] == "ed25519-minisign"

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


def test_generated_release_artifacts_match_canonical():
    content = (
        ROOT / "artifacts" / "release" / "OMG_COMPAT_CONTRACT.md"
    ).read_text(encoding="utf-8")
    assert f"version: {CANONICAL_VERSION}" in content, (
        f"OMG_COMPAT_CONTRACT.md frontmatter must have version: {CANONICAL_VERSION}"
    )


def test_cli_adapter_map_version_examples():
    content = (ROOT / "CLI-ADAPTER-MAP.md").read_text(encoding="utf-8")
    assert f"**Version:** `{CANONICAL_VERSION}`" in content, (
        f"CLI-ADAPTER-MAP.md version example must be {CANONICAL_VERSION}"
    )


# ── Inventory-driven surface existence checks ──────────────────────────────


def test_all_authored_surface_paths_exist_on_disk():
    """Every path declared in AUTHORED_SURFACES must exist in the repo.

    Uses the shared inventory — no hardcoded path lists.
    """
    missing: list[str] = []
    for path in get_authored_paths():
        if not (ROOT / path).exists():
            missing.append(path)
    assert missing == [], f"Authored surface files missing on disk: {missing}"


def test_compat_contract_snapshot_version_matches_canonical():
    """runtime/omg_compat_contract_snapshot.json contract_version must match."""
    data = _load_json(ROOT / "runtime" / "omg_compat_contract_snapshot.json")
    assert data["contract_version"] == CANONICAL_VERSION, (
        f"omg_compat_contract_snapshot.json contract_version is "
        f"{data['contract_version']!r}, expected {CANONICAL_VERSION!r}"
    )


def test_capability_schema_version_matches_canonical():
    """registry/omg-capability.schema.json version must match."""
    data = _load_json(ROOT / "registry" / "omg-capability.schema.json")
    assert data["version"] == CANONICAL_VERSION, (
        f"omg-capability.schema.json version is "
        f"{data['version']!r}, expected {CANONICAL_VERSION!r}"
    )


def test_advanced_plugin_version_matches_canonical():
    """plugins/advanced/plugin.json version must match."""
    data = _load_json(ROOT / "plugins" / "advanced" / "plugin.json")
    assert data["version"] == CANONICAL_VERSION, (
        f"plugins/advanced/plugin.json version is "
        f"{data['version']!r}, expected {CANONICAL_VERSION!r}"
    )


def test_authored_surfaces_cover_all_identity_files():
    """Spot-check that key identity files appear in AUTHORED_SURFACES.

    Uses the inventory dynamically rather than a hardcoded checklist.
    """
    surface_paths = {s.file_path for s in AUTHORED_SURFACES}
    expected_key_files = {
        "package.json",
        "settings.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "plugins/core/plugin.json",
        "plugins/advanced/plugin.json",
        "registry/omg-capability.schema.json",
        "runtime/omg_compat_contract_snapshot.json",
        "pyproject.toml",
        "CHANGELOG.md",
        "OMG_COMPAT_CONTRACT.md",
        "OMG-setup.sh",
        "hud/omg-hud.mjs",
    }
    missing = expected_key_files - surface_paths
    assert missing == set(), f"Key identity files not in AUTHORED_SURFACES: {missing}"
