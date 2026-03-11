"""Tests for the shared release surface inventory.

Verifies that runtime/release_surfaces.py is exhaustive, typed, and all
declared authored surface paths exist on disk.
"""
from __future__ import annotations

import sys
from pathlib import Path
import yaml

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from runtime.release_surfaces import (
    AUTHORED_SURFACES,
    DERIVED_SURFACE_DIRS,
    SCOPED_RESIDUE_TARGETS,
    SURFACE_TYPES,
    AuthoredSurface,
    get_authored_paths,
    get_derived_dirs,
)


# ── Expected surfaces from sync-release-identity.py ──

_EXPECTED_JSON_SURFACES: list[tuple[str, list[str | int]]] = [
    ("package.json", ["version"]),
    ("settings.json", ["_omg", "_version"]),
    ("settings.json", ["_omg", "generated", "contract_version"]),
    (".claude-plugin/plugin.json", ["version"]),
    (".claude-plugin/marketplace.json", ["version"]),
    (".claude-plugin/marketplace.json", ["metadata", "version"]),
    (".claude-plugin/marketplace.json", ["plugins", 0, "version"]),
    ("plugins/core/plugin.json", ["version"]),
    ("plugins/advanced/plugin.json", ["version"]),
    ("registry/omg-capability.schema.json", ["version"]),
]

_EXPECTED_YAML_BUNDLES: list[str] = [
    "registry/bundles/algorithms.yaml",
    "registry/bundles/api-twin.yaml",
    "registry/bundles/claim-judge.yaml",
    "registry/bundles/control-plane.yaml",
    "registry/bundles/data-lineage.yaml",
    "registry/bundles/delta-classifier.yaml",
    "registry/bundles/eval-gate.yaml",
    "registry/bundles/health.yaml",
    "registry/bundles/hook-governor.yaml",
    "registry/bundles/incident-replay.yaml",
    "registry/bundles/lsp-pack.yaml",
    "registry/bundles/mcp-fabric.yaml",
    "registry/bundles/plan-council.yaml",
    "registry/bundles/preflight.yaml",
    "registry/bundles/proof-gate.yaml",
    "registry/bundles/remote-supervisor.yaml",
    "registry/bundles/robotics.yaml",
    "registry/bundles/secure-worktree-pipeline.yaml",
    "registry/bundles/security-check.yaml",
    "registry/bundles/test-intent-lock.yaml",
    "registry/bundles/tracebank.yaml",
    "registry/bundles/vision.yaml",
]

_EXPECTED_SIX_MISSING: list[str] = [
    "OMG_COMPAT_CONTRACT.md",
    "CLI-ADAPTER-MAP.md",
    "OMG-setup.sh",
    "hud/omg-hud.mjs",
    ".claude-plugin/scripts/install.sh",
    "runtime/omg_compat_contract_snapshot.json",
]


class TestInventoryCompleteness:
    """Verify the inventory covers all known surfaces."""

    def test_authored_surfaces_is_nonempty(self) -> None:
        assert len(AUTHORED_SURFACES) > 0

    def test_total_surface_count(self) -> None:
        # 10 JSON + 1 regex(pyproject) + 22 YAML + 1 CHANGELOG
        # + 1 frontmatter + 3 CLI-ADAPTER-MAP + 1 shell + 1 js + 1 banner + 1 json
        # = 42
        assert len(AUTHORED_SURFACES) == 42

    def test_all_json_surfaces_from_sync_script_covered(self) -> None:
        """Every JSON surface from sync-release-identity.py must appear."""
        json_surfaces = [
            (s.file_path, s.field)
            for s in AUTHORED_SURFACES
            if s.surface_type == "json_key_path"
        ]
        for file_path, key_path in _EXPECTED_JSON_SURFACES:
            assert (file_path, key_path) in json_surfaces, (
                f"Missing JSON surface: {file_path} {key_path}"
            )

    def test_pyproject_toml_regex_surface(self) -> None:
        pyproject_entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "pyproject.toml"
        ]
        assert len(pyproject_entries) == 1
        assert pyproject_entries[0].surface_type == "regex_line"

    def test_changelog_surface(self) -> None:
        changelog_entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "CHANGELOG.md"
        ]
        assert len(changelog_entries) == 1
        assert changelog_entries[0].surface_type == "changelog_header"

    def test_all_22_yaml_bundles_covered(self) -> None:
        yaml_paths = {
            s.file_path
            for s in AUTHORED_SURFACES
            if s.surface_type == "yaml_line"
        }
        for bundle_path in _EXPECTED_YAML_BUNDLES:
            assert bundle_path in yaml_paths, f"Missing YAML bundle: {bundle_path}"
        assert len(yaml_paths) == 22

    def test_six_missing_surfaces_now_present(self) -> None:
        inventory_paths = {s.file_path for s in AUTHORED_SURFACES}
        for path in _EXPECTED_SIX_MISSING:
            assert path in inventory_paths, (
                f"Previously missing surface not in inventory: {path}"
            )

    def test_compat_contract_frontmatter(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "OMG_COMPAT_CONTRACT.md"
        ]
        assert len(entries) == 1
        assert entries[0].surface_type == "frontmatter_field"
        assert entries[0].field == "version"

    def test_cli_adapter_map_has_three_markers(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "CLI-ADAPTER-MAP.md"
        ]
        assert len(entries) == 3
        for e in entries:
            assert e.surface_type == "regex_line"

    def test_omg_setup_sh_shell_literal(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "OMG-setup.sh"
        ]
        assert len(entries) == 1
        assert entries[0].surface_type == "shell_literal"

    def test_hud_js_literal(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "hud/omg-hud.mjs"
        ]
        assert len(entries) == 1
        assert entries[0].surface_type == "js_literal"

    def test_install_sh_banner_literal(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == ".claude-plugin/scripts/install.sh"
        ]
        assert len(entries) == 1
        assert entries[0].surface_type == "banner_literal"

    def test_compat_snapshot_json_key_path(self) -> None:
        entries = [
            s for s in AUTHORED_SURFACES
            if s.file_path == "runtime/omg_compat_contract_snapshot.json"
        ]
        assert len(entries) == 1
        assert entries[0].surface_type == "json_key_path"
        assert entries[0].field == ["contract_version"]


class TestDiskExistence:
    """Every declared authored surface path must exist on disk."""

    def test_all_authored_paths_exist_on_disk(self) -> None:
        missing: list[str] = []
        for path in get_authored_paths():
            if not (REPO_ROOT / path).exists():
                missing.append(path)
        assert missing == [], f"Authored surface files missing on disk: {missing}"


class TestDerivedSurfaces:
    """Verify derived surface directory declarations."""

    def test_derived_surface_dirs_has_three_entries(self) -> None:
        assert len(DERIVED_SURFACE_DIRS) >= 3

    def test_derived_dirs_include_expected(self) -> None:
        expected = {"dist/", "artifacts/release/", "build/lib/"}
        assert expected.issubset(set(DERIVED_SURFACE_DIRS))

    def test_scoped_residue_targets_nonempty(self) -> None:
        assert len(SCOPED_RESIDUE_TARGETS) > 0

    def test_get_derived_dirs_returns_list(self) -> None:
        dirs = get_derived_dirs()
        assert isinstance(dirs, list)
        assert len(dirs) >= 3


class TestHelpers:
    """Verify helper function behavior."""

    def test_get_authored_paths_returns_unique_paths(self) -> None:
        paths = get_authored_paths()
        assert len(paths) == len(set(paths)), "Duplicate paths in get_authored_paths()"

    def test_get_authored_paths_count(self) -> None:
        paths = get_authored_paths()
        # 37 unique files: 7 JSON files + pyproject.toml + 22 YAML + CHANGELOG
        # + OMG_COMPAT_CONTRACT + CLI-ADAPTER-MAP + OMG-setup.sh + hud/omg-hud.mjs
        # + .claude-plugin/scripts/install.sh + runtime/omg_compat_contract_snapshot.json
        assert len(paths) == 37


class TestTypeSafety:
    """Verify type constraints on surface entries."""

    def test_all_surface_types_valid(self) -> None:
        invalid = [
            (s.file_path, s.surface_type)
            for s in AUTHORED_SURFACES
            if s.surface_type not in SURFACE_TYPES
        ]
        assert invalid == [], f"Invalid surface types: {invalid}"

    def test_json_key_paths_are_lists(self) -> None:
        for s in AUTHORED_SURFACES:
            if s.surface_type == "json_key_path":
                assert isinstance(s.field, list), (
                    f"{s.file_path}: json_key_path field must be a list, got {type(s.field)}"
                )

    def test_regex_fields_are_strings(self) -> None:
        regex_types = {"regex_line", "changelog_header", "shell_literal", "js_literal", "banner_literal"}
        for s in AUTHORED_SURFACES:
            if s.surface_type in regex_types:
                assert isinstance(s.field, str), (
                    f"{s.file_path}: {s.surface_type} field must be a str, got {type(s.field)}"
                )

    def test_all_entries_have_descriptions(self) -> None:
        missing = [s.file_path for s in AUTHORED_SURFACES if not s.description]
        assert missing == [], f"Surfaces missing descriptions: {missing}"


class TestNegativeCases:
    """Verify the inventory model rejects malformed data."""

    def test_missing_surface_path_detected(self) -> None:
        """A bogus path should not appear in the inventory."""
        paths = get_authored_paths()
        assert "nonexistent/bogus/file.json" not in paths

    def test_authored_surface_is_frozen(self) -> None:
        """AuthoredSurface instances must be immutable."""
        surface = AuthoredSurface("test.json", "json_key_path", ["version"])
        with pytest.raises(AttributeError):
            surface.file_path = "other.json"  # pyright: ignore[reportAttributeAccessIssue]

    def test_no_duplicate_surface_entries(self) -> None:
        """No exact duplicate entries should exist."""
        seen: set[tuple[str, str, str]] = set()
        dupes: list[str] = []
        for s in AUTHORED_SURFACES:
            key = (s.file_path, s.surface_type, str(s.field))
            if key in seen:
                dupes.append(f"{s.file_path}:{s.surface_type}:{s.field}")
            seen.add(key)
        assert dupes == [], f"Duplicate surface entries: {dupes}"


class TestPhaseOneBundleParity:
    def test_control_plane_declares_all_canonical_hosts(self) -> None:
        bundle_path = REPO_ROOT / "registry" / "bundles" / "control-plane.yaml"
        payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert sorted(payload.get("hosts", [])) == ["claude", "codex", "gemini", "kimi"]

    def test_control_plane_policy_model_has_phase1_release_expectations(self) -> None:
        bundle_path = REPO_ROOT / "registry" / "bundles" / "control-plane.yaml"
        payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        policy_model = payload["policy_model"]
        evidence_contract = policy_model["evidence_contract"]

        for required in (
            "attestation_statement",
            "attestation_verifier",
            "claim_judge_verdict",
            "compliance_verdict",
        ):
            assert required in evidence_contract

    def test_plan_council_includes_release_audit_and_profile_review_surfaces(self) -> None:
        bundle_path = REPO_ROOT / "registry" / "bundles" / "plan-council.yaml"
        payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)

        references = payload.get("assets", {}).get("references", [])
        assert "commands/OMG:profile-review.md" in references
        assert "commands/OMG:validate.md" in references
        assert "commands/OMG:release-audit.md" in references
