"""Tests for sync-release-identity.py — authored surface sync/check flow.

Covers all surface type handlers (including 4 new types), derived directory
guard, integration with the shared release_surfaces inventory, and drift
detection via subprocess.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.adoption import CANONICAL_VERSION
from runtime.release_surfaces import (
    AUTHORED_SURFACES,
    DERIVED_SURFACE_DIRS,
    AuthoredSurface,
)


def _load_sync_module():
    """Load sync-release-identity.py as an importable module."""
    spec = importlib.util.spec_from_file_location(
        "sync_release_identity",
        str(REPO_ROOT / "scripts" / "sync-release-identity.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sync_mod = _load_sync_module()

DRIFT_VERSION = "0.0.0"


# ── Shared inventory integration ───────────────────────────────────────────


class TestSharedInventory:
    """Script must use AUTHORED_SURFACES, not hardcoded lists."""

    def test_no_json_surfaces_constant(self) -> None:
        assert not hasattr(sync_mod, "JSON_SURFACES")

    def test_no_regex_surfaces_constant(self) -> None:
        assert not hasattr(sync_mod, "REGEX_SURFACES")

    def test_no_yaml_bundle_dir_constant(self) -> None:
        assert not hasattr(sync_mod, "YAML_BUNDLE_DIR")

    def test_no_changelog_file_constant(self) -> None:
        assert not hasattr(sync_mod, "CHANGELOG_FILE")

    def test_imports_from_release_surfaces(self) -> None:
        source = (REPO_ROOT / "scripts" / "sync-release-identity.py").read_text()
        assert "runtime.release_surfaces" in source


# ── Derived directory guard ────────────────────────────────────────────────


class TestDerivedDirectoryGuard:
    """Guard prevents mutation of generated directories."""

    def test_no_authored_surface_in_derived_dirs(self) -> None:
        for surface in AUTHORED_SURFACES:
            for d in DERIVED_SURFACE_DIRS:
                assert not surface.file_path.startswith(d), (
                    f"{surface.file_path} inside derived dir {d}"
                )

    def test_update_refuses_derived_dir(self, tmp_path: Path) -> None:
        surface = AuthoredSurface("dist/test.json", "json_key_path", ["version"])
        with pytest.raises(ValueError, match="derived"):
            sync_mod.update_surface(tmp_path, surface, CANONICAL_VERSION)

    def test_check_refuses_derived_dir(self, tmp_path: Path) -> None:
        surface = AuthoredSurface("dist/test.json", "json_key_path", ["version"])
        with pytest.raises(ValueError, match="derived"):
            sync_mod.check_surface(tmp_path, surface, CANONICAL_VERSION)


# ── frontmatter_field handler ──────────────────────────────────────────────


class TestFrontmatterField:
    """Tests for frontmatter_field surface type."""

    def _make(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "doc.md"
        p.write_text(
            f"---\ntitle: Test\nversion: {version}\nstatus: active\n---\n\n# Body\n"
        )
        return p

    def test_check_detects_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("doc.md", "frontmatter_field", "version", "test")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_check_no_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, CANONICAL_VERSION)
        s = AuthoredSurface("doc.md", "frontmatter_field", "version", "test")
        assert sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION) == []

    def test_update_fixes_drift(self, tmp_path: Path) -> None:
        fp = self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("doc.md", "frontmatter_field", "version", "test")
        assert len(sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)) == 1
        content = fp.read_text()
        assert f"version: {CANONICAL_VERSION}" in content
        assert "title: Test" in content
        assert "# Body" in content


# ── shell_literal handler ──────────────────────────────────────────────────


class TestShellLiteral:
    """Tests for shell_literal surface type."""

    def _make(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "test.sh"
        p.write_text(f'#!/bin/bash\nVERSION="{version}"\necho "$VERSION"\n')
        return p

    def test_check_detects_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("test.sh", "shell_literal", r'^VERSION="(.+?)"', "test")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_check_no_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, CANONICAL_VERSION)
        s = AuthoredSurface("test.sh", "shell_literal", r'^VERSION="(.+?)"', "test")
        assert sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION) == []

    def test_update_fixes_drift(self, tmp_path: Path) -> None:
        fp = self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("test.sh", "shell_literal", r'^VERSION="(.+?)"', "test")
        assert len(sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)) == 1
        assert f'VERSION="{CANONICAL_VERSION}"' in fp.read_text()


# ── js_literal handler ─────────────────────────────────────────────────────


class TestJsLiteral:
    """Tests for js_literal surface type."""

    def _make(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "test.mjs"
        p.write_text(f'function v() {{\n  return "{version}";\n}}\n')
        return p

    def test_check_detects_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("test.mjs", "js_literal", r'return "(\d+\.\d+\.\d+)"', "t")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_check_no_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, CANONICAL_VERSION)
        s = AuthoredSurface("test.mjs", "js_literal", r'return "(\d+\.\d+\.\d+)"', "t")
        assert sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION) == []

    def test_update_fixes_drift(self, tmp_path: Path) -> None:
        fp = self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("test.mjs", "js_literal", r'return "(\d+\.\d+\.\d+)"', "t")
        assert len(sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)) == 1
        assert f'return "{CANONICAL_VERSION}"' in fp.read_text()


# ── banner_literal handler ─────────────────────────────────────────────────


class TestBannerLiteral:
    """Tests for banner_literal surface type."""

    def _make(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "install.sh"
        p.write_text(f'#!/bin/bash\necho "Installer v{version}"\necho "done"\n')
        return p

    def test_check_detects_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("install.sh", "banner_literal", r'v(\d+\.\d+\.\d+)', "t")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_check_no_drift(self, tmp_path: Path) -> None:
        self._make(tmp_path, CANONICAL_VERSION)
        s = AuthoredSurface("install.sh", "banner_literal", r'v(\d+\.\d+\.\d+)', "t")
        assert sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION) == []

    def test_update_fixes_drift(self, tmp_path: Path) -> None:
        fp = self._make(tmp_path, DRIFT_VERSION)
        s = AuthoredSurface("install.sh", "banner_literal", r'v(\d+\.\d+\.\d+)', "t")
        assert len(sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)) == 1
        assert f"v{CANONICAL_VERSION}" in fp.read_text()


# ── Existing surface types preserved ───────────────────────────────────────


class TestExistingSurfaceTypes:
    """Existing handlers (json, regex, yaml, changelog) still work."""

    def test_json_key_path_check_drift(self, tmp_path: Path) -> None:
        (tmp_path / "t.json").write_text(json.dumps({"version": DRIFT_VERSION}))
        s = AuthoredSurface("t.json", "json_key_path", ["version"], "test")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_json_key_path_update(self, tmp_path: Path) -> None:
        fp = tmp_path / "t.json"
        fp.write_text(json.dumps({"version": DRIFT_VERSION}))
        s = AuthoredSurface("t.json", "json_key_path", ["version"], "test")
        sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)
        assert json.loads(fp.read_text())["version"] == CANONICAL_VERSION

    def test_json_nested_key_path(self, tmp_path: Path) -> None:
        fp = tmp_path / "t.json"
        fp.write_text(json.dumps({"meta": {"version": DRIFT_VERSION}}))
        s = AuthoredSurface("t.json", "json_key_path", ["meta", "version"], "test")
        sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)
        assert json.loads(fp.read_text())["meta"]["version"] == CANONICAL_VERSION

    def test_regex_line_check_drift(self, tmp_path: Path) -> None:
        (tmp_path / "p.toml").write_text(f'version = "{DRIFT_VERSION}"\n')
        s = AuthoredSurface("p.toml", "regex_line", r'^version = "(.+?)"', "test")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_regex_line_update(self, tmp_path: Path) -> None:
        fp = tmp_path / "p.toml"
        fp.write_text(f'version = "{DRIFT_VERSION}"\n')
        s = AuthoredSurface("p.toml", "regex_line", r'^version = "(.+?)"', "test")
        sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)
        assert f'version = "{CANONICAL_VERSION}"' in fp.read_text()

    def test_yaml_line_check_drift(self, tmp_path: Path) -> None:
        (tmp_path / "b.yaml").write_text(f"name: test\nversion: {DRIFT_VERSION}\n")
        s = AuthoredSurface("b.yaml", "yaml_line", "version", "test")
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_yaml_line_update(self, tmp_path: Path) -> None:
        fp = tmp_path / "b.yaml"
        fp.write_text(f"name: test\nversion: {DRIFT_VERSION}\n")
        s = AuthoredSurface("b.yaml", "yaml_line", "version", "test")
        sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)
        assert f"version: {CANONICAL_VERSION}" in fp.read_text()

    def test_changelog_header_check_drift(self, tmp_path: Path) -> None:
        (tmp_path / "CL.md").write_text(f"# Log\n\n## {DRIFT_VERSION}\n\n- Fix\n")
        s = AuthoredSurface(
            "CL.md", "changelog_header", r"^## \[?(\d+\.\d+\.\d+)\]?", "test"
        )
        assert len(sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)) == 1

    def test_changelog_header_update_preserves_date(self, tmp_path: Path) -> None:
        fp = tmp_path / "CL.md"
        fp.write_text(f"# Log\n\n## [{DRIFT_VERSION}] - 2024-01-01\n\n- Fix\n")
        s = AuthoredSurface(
            "CL.md", "changelog_header", r"^## \[?(\d+\.\d+\.\d+)\]?", "test"
        )
        sync_mod.update_surface(tmp_path, s, CANONICAL_VERSION)
        content = fp.read_text()
        assert f"## [{CANONICAL_VERSION}]" in content
        assert "2024-01-01" in content


# ── Drift reporting ────────────────────────────────────────────────────────


class TestDriftReporting:
    """Drift check returns meaningful current values."""

    def test_frontmatter_drift_reports_value(self, tmp_path: Path) -> None:
        (tmp_path / "d.md").write_text("---\nversion: 9.9.9\n---\n")
        s = AuthoredSurface("d.md", "frontmatter_field", "version", "test")
        drifts = sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)
        assert drifts[0][1] == "9.9.9"

    def test_shell_drift_reports_value(self, tmp_path: Path) -> None:
        (tmp_path / "s.sh").write_text('VERSION="9.8.7"\n')
        s = AuthoredSurface("s.sh", "shell_literal", r'^VERSION="(.+?)"', "test")
        drifts = sync_mod.check_surface(tmp_path, s, CANONICAL_VERSION)
        assert drifts[0][1] == "9.8.7"


# ── Integration (subprocess) ──────────────────────────────────────────────


class TestIntegration:
    """Subprocess tests for --check mode."""

    def test_check_exits_zero_on_real_repo(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "sync-release-identity.py"),
                "--check",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_output_mentions_sync(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "sync-release-identity.py"),
                "--check",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert "in sync" in result.stdout.lower()
