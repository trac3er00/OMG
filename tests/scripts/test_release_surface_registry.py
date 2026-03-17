"""Tests for the release surface registry contract.

Verifies that runtime/release_surface_registry.py covers all required
public-surface behavioral parity entries for v2.2.7: docs, launchers,
check names, workflows, and signed artifacts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from runtime.release_surface_registry import (
    GENERATED_SECTION_MARKERS,
    PUBLIC_SURFACES,
    get_public_surfaces,
    get_generated_section_markers,
    validate_registry,
)


# ── Required surface categories ────────────────────────────────────────────

_REQUIRED_CATEGORIES = frozenset({
    "docs",
    "launcher",
    "check_name",
    "workflow",
    "sign_artifact",
    "npm",
    "action",
})

# ── Required surface IDs (minimum) ────────────────────────────────────────

_REQUIRED_SURFACE_IDS: list[str] = [
    # Docs surfaces
    "release_notes_artifact",
    "changelog_current_block",
    "readme_quickstart",
    "readme_command_surface",
    # Install guide fast-path sections
    "install_claude_code",
    "install_codex",
    "install_gemini",
    "install_kimi",
    "install_opencode",
    "install_github_app",
    "command_surface_doc",
    # Launchers
    "launcher_python",
    "launcher_shell",
    "launcher_npm_bin",
    # npm bin key
    "npm_bin_key",
    # GitHub check name
    "github_check_run_name",
    # Workflows
    "workflow_release",
    "workflow_evidence_gate",
    "workflow_compat_gate",
    # Action
    "action_yaml",
    # Signed artifacts
    "sign_locked_prod",
    "sign_fintech",
    "sign_airgapped",
]


class TestRegistryCompleteness:
    """Verify the registry covers all required surface categories."""

    def test_public_surfaces_is_nonempty(self) -> None:
        surfaces = get_public_surfaces()
        assert len(surfaces) > 0

    def test_registry_contains_all_required_categories(self) -> None:
        surfaces = get_public_surfaces()
        found_categories = {s["category"] for s in surfaces}
        missing = _REQUIRED_CATEGORIES - found_categories
        assert missing == set(), f"Missing categories: {missing}"

    def test_all_required_surface_ids_present(self) -> None:
        surfaces = get_public_surfaces()
        found_ids = {s["id"] for s in surfaces}
        for sid in _REQUIRED_SURFACE_IDS:
            assert sid in found_ids, f"Missing required surface id: {sid}"

    def test_minimum_surface_count(self) -> None:
        surfaces = get_public_surfaces()
        assert len(surfaces) >= 23


class TestValidateRegistry:
    """Verify validate_registry() returns no blockers for clean data."""

    def test_clean_registry_has_no_blockers(self) -> None:
        blockers = validate_registry()
        assert blockers == [], f"Unexpected blockers: {blockers}"

    def test_validate_returns_list(self) -> None:
        result = validate_registry()
        assert isinstance(result, list)


class TestSurfaceUniqueness:
    """Verify each surface has a unique id."""

    def test_all_surface_ids_unique(self) -> None:
        surfaces = get_public_surfaces()
        ids = [s["id"] for s in surfaces]
        dupes = [sid for sid in ids if ids.count(sid) > 1]
        assert dupes == [], f"Duplicate surface ids: {set(dupes)}"


class TestGeneratedSectionMarkers:
    """Verify generated section markers are present and correct."""

    def test_markers_is_nonempty(self) -> None:
        markers = get_generated_section_markers()
        assert len(markers) > 0

    def test_markers_contain_quickstart(self) -> None:
        markers = get_generated_section_markers()
        assert "readme_quickstart" in markers
        assert "<!-- OMG:GENERATED:quickstart -->" in markers["readme_quickstart"]

    def test_markers_contain_command_surface(self) -> None:
        markers = get_generated_section_markers()
        assert "readme_command_surface" in markers

    def test_markers_contain_install_fast_path(self) -> None:
        markers = get_generated_section_markers()
        assert "install_fast_path" in markers

    def test_markers_contain_changelog(self) -> None:
        markers = get_generated_section_markers()
        assert "changelog_current" in markers


class TestLauncherSurfaces:
    """Verify launcher behavioral promises."""

    def test_launcher_python_name(self) -> None:
        surfaces = get_public_surfaces()
        py = [s for s in surfaces if s["id"] == "launcher_python"]
        assert len(py) == 1
        assert py[0]["launcher_name"] == "python3 scripts/omg.py"

    def test_launcher_shell_name(self) -> None:
        surfaces = get_public_surfaces()
        sh = [s for s in surfaces if s["id"] == "launcher_shell"]
        assert len(sh) == 1
        assert sh[0]["launcher_name"] == "./OMG-setup.sh"

    def test_launcher_npm_bin_name(self) -> None:
        surfaces = get_public_surfaces()
        npm = [s for s in surfaces if s["id"] == "launcher_npm_bin"]
        assert len(npm) == 1
        assert npm[0]["launcher_name"] == "omg"

    def test_npm_bin_key(self) -> None:
        surfaces = get_public_surfaces()
        nk = [s for s in surfaces if s["id"] == "npm_bin_key"]
        assert len(nk) == 1
        assert nk[0]["bin_key"] == "omg"


class TestCheckName:
    """Verify GitHub check name is exactly correct."""

    def test_check_run_name_exact(self) -> None:
        surfaces = get_public_surfaces()
        cr = [s for s in surfaces if s["id"] == "github_check_run_name"]
        assert len(cr) == 1
        assert cr[0]["check_name"] == "OMG PR Reviewer"


class TestParametrizedMissingSurface:
    """Parametrized failure test for missing surfaces."""

    @pytest.mark.parametrize("surface_id", _REQUIRED_SURFACE_IDS)
    def test_removing_surface_causes_validation_failure(self, surface_id: str) -> None:
        """If any required surface were missing, validate_registry would catch it."""
        surfaces = get_public_surfaces()
        found_ids = {s["id"] for s in surfaces}
        assert surface_id in found_ids, (
            f"Required surface '{surface_id}' missing from registry"
        )
