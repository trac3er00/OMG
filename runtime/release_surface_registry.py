"""Release surface registry contract for public-surface behavioral parity.

Single source of truth for all PUBLIC behavioral surfaces in OMG — doc markers,
launchers, check names, workflow entrypoints, and signed artifacts. Completely
separate from the version-only runtime/release_surfaces.py.

Consumers:
    - runtime/contract_compiler.py  (drift gate, compile checks)
    - tests/scripts/test_release_surface_registry.py (parity assertions)
"""
from typing import Any

PublicSurface = dict[str, Any]


GENERATED_SECTION_MARKERS: dict[str, str] = {
    "install_fast_path": "<!-- OMG:GENERATED:install-fast-path -->",
    "changelog_current": "<!-- OMG:GENERATED:changelog-v2.3.0 -->",
    "command_surface_doc": "<!-- OMG:GENERATED:command-surface -->",
    "install_intro": "<!-- OMG:GENERATED:install-intro -->",
    "why_omg": "<!-- OMG:GENERATED:why-omg -->",
    "proof_quickstart": "<!-- OMG:GENERATED:proof-quickstart -->",
    "quick_reference_hosts": "<!-- OMG:GENERATED:quick-reference-hosts -->",
    "verification_index_targets": "<!-- OMG:GENERATED:verification-index-targets -->",
}

_INSTALL_GUIDES: list[tuple[str, str]] = [
    ("install_claude_code", "docs/install/claude-code.md"),
    ("install_codex", "docs/install/codex.md"),
    ("install_gemini", "docs/install/gemini.md"),
    ("install_kimi", "docs/install/kimi.md"),
    ("install_opencode", "docs/install/opencode.md"),
    ("install_github_app", "docs/install/github-app.md"),
]

PUBLIC_SURFACES: list[PublicSurface] = [
    {
        "id": "release_notes_artifact",
        "category": "docs",
        "path": "artifacts/release/release-notes-v2.3.0.md",
        "description": "release notes artifact for v2.3.0",
    },
    {
        "id": "changelog_current_block",
        "category": "docs",
        "path": "CHANGELOG.md",
        "marker": "<!-- OMG:GENERATED:changelog-v2.3.0 -->",
        "description": "current release block in changelog",
    },
    *[
        {
            "id": guide_id,
            "category": "docs",
            "path": guide_path,
            "marker": "<!-- OMG:GENERATED:install-fast-path -->",
            "description": f"install fast-path section in {guide_path}",
        }
        for guide_id, guide_path in _INSTALL_GUIDES
    ],
    {
        "id": "command_surface_doc",
        "category": "docs",
        "path": "docs/command-surface.md",
        "marker": "<!-- OMG:GENERATED:command-surface -->",
        "description": "command surface reference doc",
    },
    {
        "id": "github_release_body_artifact",
        "category": "release_body",
        "path": "artifacts/release/github-release-body.md",
        "description": "GitHub release body text for tag publish",
    },
    {
        "id": "tag_body_artifact",
        "category": "release_body",
        "path": "artifacts/release/tag-body.md",
        "description": "annotated tag body text for release",
    },
    {
        "id": "install_intro",
        "category": "docs",
        "path": "README.md",
        "marker": "<!-- OMG:GENERATED:install-intro -->",
        "description": "authoritative install intro section in README",
    },
    {
        "id": "why_omg",
        "category": "docs",
        "path": "README.md",
        "marker": "<!-- OMG:GENERATED:why-omg -->",
        "description": "authoritative why-omg section in README",
    },
    {
        "id": "proof_quickstart",
        "category": "docs",
        "path": "docs/proof.md",
        "marker": "<!-- OMG:GENERATED:proof-quickstart -->",
        "description": "proof quickstart section in proof docs",
    },
    {
        "id": "quick_reference_hosts",
        "category": "docs",
        "path": "QUICK-REFERENCE.md",
        "marker": "<!-- OMG:GENERATED:quick-reference-hosts -->",
        "description": "host table in quick reference",
    },
    {
        "id": "verification_index_targets",
        "category": "docs",
        "path": "INSTALL-VERIFICATION-INDEX.md",
        "marker": "<!-- OMG:GENERATED:verification-index-targets -->",
        "description": "installation targets in verification index",
    },
    {
        "id": "launcher_python",
        "category": "launcher",
        "launcher_name": "python3 scripts/omg.py",
        "scope": "internal",
        "description": "Python launcher",
    },
    {
        "id": "launcher_shell",
        "category": "launcher",
        "launcher_name": "./OMG-setup.sh",
        "scope": "internal",
        "description": "Shell setup launcher",
    },
    {
        "id": "launcher_npm_bin",
        "category": "launcher",
        "launcher_name": "omg",
        "scope": "public",
        "description": "npm bin launcher",
    },
    {
        "id": "npm_bin_key",
        "category": "npm",
        "bin_key": "omg",
        "description": "npm package.json bin key",
    },
    {
        "id": "github_check_run_name",
        "category": "check_name",
        "check_name": "OMG PR Reviewer",
        "description": "immutable GitHub check-run name",
    },
    {
        "id": "workflow_release",
        "category": "workflow",
        "path": ".github/workflows/release.yml",
        "description": "release workflow entrypoint",
    },
    {
        "id": "workflow_evidence_gate",
        "category": "workflow",
        "path": ".github/workflows/evidence-gate.yml",
        "description": "evidence gate workflow",
    },
    {
        "id": "workflow_compat_gate",
        "category": "workflow",
        "path": ".github/workflows/omg-compat-gate.yml",
        "description": "compat gate workflow",
    },
    {
        "id": "action_yaml",
        "category": "action",
        "path": "action.yml",
        "description": "GitHub Action entrypoint",
    },
    {
        "id": "sign_locked_prod",
        "category": "sign_artifact",
        "path": "registry/policy-packs/locked-prod.signature.json",
        "description": "locked-prod policy pack signature",
    },
    {
        "id": "sign_fintech",
        "category": "sign_artifact",
        "path": "registry/policy-packs/fintech.signature.json",
        "description": "fintech policy pack signature",
    },
    {
        "id": "sign_airgapped",
        "category": "sign_artifact",
        "path": "registry/policy-packs/airgapped.signature.json",
        "description": "airgapped policy pack signature",
    },
]

_REQUIRED_IDS: frozenset[str] = frozenset({
    "release_notes_artifact",
    "changelog_current_block",
    "install_claude_code",
    "install_codex",
    "install_gemini",
    "install_kimi",
    "install_opencode",
    "install_github_app",
    "command_surface_doc",
    "github_release_body_artifact",
    "tag_body_artifact",
    "launcher_python",
    "launcher_shell",
    "launcher_npm_bin",
    "npm_bin_key",
    "github_check_run_name",
    "workflow_release",
    "workflow_evidence_gate",
    "workflow_compat_gate",
    "action_yaml",
    "sign_locked_prod",
    "sign_fintech",
    "sign_airgapped",
    "install_intro",
    "why_omg",
    "proof_quickstart",
    "quick_reference_hosts",
    "verification_index_targets",
})

_REQUIRED_CATEGORIES: frozenset[str] = frozenset({
    "docs",
    "launcher",
    "check_name",
    "workflow",
    "sign_artifact",
    "npm",
    "action",
    "release_body",
})

PROMOTED_PUBLIC_COMMANDS: list[str] = [
    "omg ship",
    "omg proof",
    "omg blocked --last",
    "omg explain run --run-id <id>",
    "omg budget simulate --enforce",
    "omg install --plan",
    "omg install --apply",
    "omg doctor",
    "omg env doctor",
]


def get_public_surfaces() -> list[PublicSurface]:
    return list(PUBLIC_SURFACES)


def get_generated_section_markers() -> dict[str, str]:
    return dict(GENERATED_SECTION_MARKERS)


def get_promoted_public_commands() -> list[str]:
    return list(PROMOTED_PUBLIC_COMMANDS)


def validate_registry() -> list[str]:
    blockers: list[str] = []

    found_ids = {s["id"] for s in PUBLIC_SURFACES}
    missing_ids = _REQUIRED_IDS - found_ids
    if missing_ids:
        blockers.append(f"missing required surface ids: {sorted(missing_ids)}")

    found_categories = {s["category"] for s in PUBLIC_SURFACES}
    missing_cats = _REQUIRED_CATEGORIES - found_categories
    if missing_cats:
        blockers.append(f"missing required categories: {sorted(missing_cats)}")

    ids_list = [s["id"] for s in PUBLIC_SURFACES]
    dupes = {sid for sid in ids_list if ids_list.count(sid) > 1}
    if dupes:
        blockers.append(f"duplicate surface ids: {sorted(dupes)}")

    crazy_commands = [c for c in PROMOTED_PUBLIC_COMMANDS if "crazy" in c.lower()]
    if crazy_commands:
        blockers.append(
            f"/OMG:crazy is compatibility-only and must not appear in "
            f"PROMOTED_PUBLIC_COMMANDS: {crazy_commands}"
        )

    return blockers
