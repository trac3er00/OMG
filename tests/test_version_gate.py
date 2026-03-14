"""
Version Gate — comprehensive pre-publish version consistency enforcement.

This test suite is the mandatory gate that must pass before any version is
published to npm or PyPI.  It verifies EVERY version surface — authored,
derived, and runtime-generated — against the single source of truth in
runtime/adoption.py::CANONICAL_VERSION.

Run manually:
    pytest tests/test_version_gate.py -v

Run as part of full suite:
    pytest

How to fix failures:
1. Authored surfaces  → run  python3 scripts/sync-release-identity.py
2. Manifest/dist      → run  python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel public
                       and   python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel enterprise
3. artifacts/release  → same as above with --output-root artifacts/release  (omit --output-root)
4. build/ artifacts   → run  python3 -m build --wheel
5. .gemini/.kimi      → update _omg._version and _omg.generated.contract_version manually
6. Final check        → python3 scripts/validate-release-identity.py --scope all  (must exit 0)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Import canonical version from the single source of truth
sys.path.insert(0, str(ROOT))
from runtime.adoption import CANONICAL_VERSION  # noqa: E402
from runtime.canonical_surface import get_canonical_hosts  # noqa: E402


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _read_json(rel: str) -> dict[str, Any]:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _read_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _version_label(path: str) -> str:
    return f"{path} must be {CANONICAL_VERSION}"


def _require_generated_path(path: Path, rel: str, fix_hint: str) -> Path:
    assert path.exists(), f"{rel} missing.\nFix: {fix_hint}"
    return path


def _compile_host_flags() -> str:
    return " ".join(f"--host {host}" for host in get_canonical_hosts())


def _compile_fix_hint(channel: str, output_root: str | None = None) -> str:
    command = f"python3 scripts/omg.py contract compile {_compile_host_flags()} --channel {channel}"
    if output_root:
        command += f" --output-root {output_root}"
    return command


# ─────────────────────────────────────────────
# 1. Core authored surfaces
# ─────────────────────────────────────────────

def test_gate_package_json():
    pkg = _read_json("package.json")
    assert pkg["version"] == CANONICAL_VERSION, _version_label("package.json")


def test_gate_pyproject_toml():
    text = _read_text("pyproject.toml")
    assert f'version = "{CANONICAL_VERSION}"' in text, _version_label("pyproject.toml")


def test_gate_settings_json():
    s = _read_json("settings.json")
    assert s["_omg"]["_version"] == CANONICAL_VERSION, _version_label("settings.json _omg._version")
    assert s["_omg"]["generated"]["contract_version"] == CANONICAL_VERSION, \
        _version_label("settings.json _omg.generated.contract_version")


def test_gate_claude_plugin_json():
    p = _read_json(".claude-plugin/plugin.json")
    assert p["version"] == CANONICAL_VERSION, _version_label(".claude-plugin/plugin.json")


def test_gate_claude_marketplace_json():
    m = _read_json(".claude-plugin/marketplace.json")
    assert m["version"] == CANONICAL_VERSION, _version_label(".claude-plugin/marketplace.json")
    assert m["metadata"]["version"] == CANONICAL_VERSION, \
        _version_label(".claude-plugin/marketplace.json metadata.version")
    assert m["plugins"][0]["version"] == CANONICAL_VERSION, \
        _version_label(".claude-plugin/marketplace.json plugins[0].version")


def test_gate_plugins_core_json():
    p = _read_json("plugins/core/plugin.json")
    assert p["version"] == CANONICAL_VERSION, _version_label("plugins/core/plugin.json")


def test_gate_plugins_advanced_json():
    p = _read_json("plugins/advanced/plugin.json")
    assert p["version"] == CANONICAL_VERSION, _version_label("plugins/advanced/plugin.json")


def test_gate_registry_schema_version():
    s = _read_json("registry/omg-capability.schema.json")
    assert s["version"] == CANONICAL_VERSION, _version_label("registry/omg-capability.schema.json")


def test_gate_compat_contract_snapshot():
    s = _read_json("runtime/omg_compat_contract_snapshot.json")
    assert s["contract_version"] == CANONICAL_VERSION, \
        _version_label("runtime/omg_compat_contract_snapshot.json")


# ─────────────────────────────────────────────
# 2. All registry bundles
# ─────────────────────────────────────────────

_BUNDLE_DIR = ROOT / "registry" / "bundles"


@pytest.mark.parametrize("bundle_file", sorted(_BUNDLE_DIR.glob("*.yaml")))
def test_gate_registry_bundle_version(bundle_file: Path):
    """Every registry bundle yaml must declare version: CANONICAL_VERSION."""
    text = bundle_file.read_text(encoding="utf-8")
    assert f"version: {CANONICAL_VERSION}" in text, \
        f"{bundle_file.name}: version must be {CANONICAL_VERSION}"


# ─────────────────────────────────────────────
# 3. Runtime consumer surfaces
# ─────────────────────────────────────────────

def test_gate_omg_setup_sh():
    text = _read_text("OMG-setup.sh")
    assert f'VERSION="{CANONICAL_VERSION}"' in text, _version_label("OMG-setup.sh")


def test_gate_hud_mjs_fallback():
    text = _read_text("hud/omg-hud.mjs")
    assert f'return "{CANONICAL_VERSION}"' in text, \
        _version_label("hud/omg-hud.mjs static fallback")


def test_gate_install_sh_banner():
    text = _read_text(".claude-plugin/scripts/install.sh")
    assert f"v{CANONICAL_VERSION}" in text, _version_label(".claude-plugin/scripts/install.sh banner")


def test_gate_compat_contract_md():
    text = _read_text("OMG_COMPAT_CONTRACT.md")
    assert f"version: {CANONICAL_VERSION}" in text, _version_label("OMG_COMPAT_CONTRACT.md frontmatter")


def test_gate_cli_adapter_map():
    text = _read_text("CLI-ADAPTER-MAP.md")
    assert f"**Version:** `{CANONICAL_VERSION}`" in text, _version_label("CLI-ADAPTER-MAP.md")


# ─────────────────────────────────────────────
# 4. Derived dist/ manifests (regenerated by contract compile)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("manifest_path", [
    "dist/public/manifest.json",
    "dist/enterprise/manifest.json",
    "artifacts/release/dist/public/manifest.json",
    "artifacts/release/dist/enterprise/manifest.json",
])
def test_gate_manifest_contract_version(manifest_path: str):
    """All compiled manifests must have contract_version == CANONICAL_VERSION.

    Fix: run  python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel <channel>
              python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel <channel> --output-root artifacts/release
    """
    p = _require_generated_path(
        ROOT / manifest_path,
        manifest_path,
        _compile_fix_hint(
            "public" if "public" in manifest_path else "enterprise",
            "artifacts/release" if manifest_path.startswith("artifacts/release/") else None,
        ),
    )
    manifest = json.loads(p.read_text(encoding="utf-8"))
    assert manifest["contract_version"] == CANONICAL_VERSION, \
        (
            f"{manifest_path}: contract_version is {manifest['contract_version']!r}, "
            f"expected {CANONICAL_VERSION!r}.\n"
            f"Fix: {_compile_fix_hint('public' if 'public' in manifest_path else 'enterprise')}"
        )


@pytest.mark.parametrize("manifest_path", [
    "dist/public/manifest.json",
    "dist/enterprise/manifest.json",
    "artifacts/release/dist/public/manifest.json",
    "artifacts/release/dist/enterprise/manifest.json",
])
def test_gate_manifest_attestations_present(manifest_path: str):
    """Compiled manifests must include ed25519 attestations for all artifacts."""
    p = _require_generated_path(
        ROOT / manifest_path,
        manifest_path,
        _compile_fix_hint(
            "public" if "public" in manifest_path else "enterprise",
            "artifacts/release" if manifest_path.startswith("artifacts/release/") else None,
        ),
    )
    manifest = json.loads(p.read_text(encoding="utf-8"))
    attestations = manifest.get("attestations", [])
    artifacts = manifest.get("artifacts", [])
    assert len(attestations) == len(artifacts), \
        f"{manifest_path}: attestations count ({len(attestations)}) != artifacts count ({len(artifacts)})"
    for row in attestations:
        assert row.get("algorithm") == "ed25519-minisign", \
            f"{manifest_path}: attestation algorithm must be ed25519-minisign"


# ─────────────────────────────────────────────
# 5. Derived bundle/ files inside dist/
# ─────────────────────────────────────────────

_DIST_BUNDLE_DIRS = [
    "dist/public/bundle",
    "dist/enterprise/bundle",
    "artifacts/release/dist/public/bundle",
    "artifacts/release/dist/enterprise/bundle",
]


@pytest.mark.parametrize("bundle_root", _DIST_BUNDLE_DIRS)
def test_gate_dist_bundle_settings_version(bundle_root: str):
    p = _require_generated_path(
        ROOT / bundle_root / "settings.json",
        f"{bundle_root}/settings.json",
        _compile_fix_hint(
            "public" if "public" in bundle_root else "enterprise",
            "artifacts/release" if bundle_root.startswith("artifacts/release/") else None,
        ),
    )
    s = json.loads(p.read_text(encoding="utf-8"))
    assert s["_omg"]["_version"] == CANONICAL_VERSION, \
        _version_label(f"{bundle_root}/settings.json")


@pytest.mark.parametrize("bundle_root", _DIST_BUNDLE_DIRS)
def test_gate_dist_bundle_plugin_json_version(bundle_root: str):
    p = _require_generated_path(
        ROOT / bundle_root / ".claude-plugin" / "plugin.json",
        f"{bundle_root}/.claude-plugin/plugin.json",
        _compile_fix_hint(
            "public" if "public" in bundle_root else "enterprise",
            "artifacts/release" if bundle_root.startswith("artifacts/release/") else None,
        ),
    )
    plugin = json.loads(p.read_text(encoding="utf-8"))
    assert plugin["version"] == CANONICAL_VERSION, \
        _version_label(f"{bundle_root}/.claude-plugin/plugin.json")


# ─────────────────────────────────────────────
# 6. build/ artifacts (regenerated by python -m build)
# ─────────────────────────────────────────────

def test_gate_build_lib_adoption_version():
    """build/lib/runtime/adoption.py must export the canonical version.

    Fix: python3 -m build --wheel
    """
    p = _require_generated_path(
        ROOT / "build" / "lib" / "runtime" / "adoption.py",
        "build/lib/runtime/adoption.py",
        "python3 -m build --wheel",
    )
    text = p.read_text(encoding="utf-8")
    assert f'CANONICAL_VERSION = "{CANONICAL_VERSION}"' in text, \
        (
            f"build/lib/runtime/adoption.py CANONICAL_VERSION is stale.\n"
            f"Fix: python3 -m build --wheel"
        )


# ─────────────────────────────────────────────
# 7. Host-specific generated configs
# ─────────────────────────────────────────────

@pytest.mark.parametrize("config_path", [
    ".gemini/settings.json",
    ".kimi/mcp.json",
])
def test_gate_host_config_version(config_path: str):
    """Gemini and Kimi generated configs must carry the canonical version."""
    p = _require_generated_path(
        ROOT / config_path,
        config_path,
        "python3 scripts/sync-release-identity.py",
    )
    data = json.loads(p.read_text(encoding="utf-8"))
    omg = data.get("_omg", {})
    assert omg.get("_version") == CANONICAL_VERSION, \
        _version_label(f"{config_path} _omg._version")
    assert omg.get("generated", {}).get("contract_version") == CANONICAL_VERSION, \
        _version_label(f"{config_path} _omg.generated.contract_version")


# ─────────────────────────────────────────────
# 8. Master validator script (integration gate)
# ─────────────────────────────────────────────

def test_gate_validate_release_identity_exits_zero():
    """python3 scripts/validate-release-identity.py --scope all must exit 0.

    This is the canonical release gate used by the CI publish workflow.
    If this test fails, all other individual tests above will also fail and
    point to the exact surface that needs fixing.
    """
    result = subprocess.run(
        [sys.executable, "scripts/validate-release-identity.py", "--scope", "all"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        try:
            report = json.loads(result.stdout)
            blockers = (
                report.get("authored", {}).get("blockers", []) +
                report.get("derived", {}).get("blockers", [])
            )
            details = "\n".join(
                f"  • {b['surface']}: found {b['found']!r}, expected {b['expected']!r}"
                for b in blockers
            )
        except (json.JSONDecodeError, KeyError):
            details = result.stdout or result.stderr
        pytest.fail(
            f"validate-release-identity.py --scope all FAILED (exit {result.returncode}).\n"
            f"Stale surfaces:\n{details}\n\n"
            f"Quick fix sequence:\n"
            f"  1. python3 scripts/sync-release-identity.py\n"
            f"  2. {_compile_fix_hint('public')}\n"
            f"  3. {_compile_fix_hint('enterprise')}\n"
            f"  4. {_compile_fix_hint('public', 'artifacts/release')}\n"
            f"  5. {_compile_fix_hint('enterprise', 'artifacts/release')}\n"
            f"  6. python3 -m build --wheel\n"
        )
