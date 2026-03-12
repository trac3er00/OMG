"""Shared release surface inventory.

Single audited source of truth for all version surfaces in the OMG project.
This module describes WHERE version strings appear and HOW to find/update them.

It does NOT import runtime.adoption or encode the canonical version value.
The canonical version lives solely in runtime/adoption.py:CANONICAL_VERSION.

Consumers:
    - scripts/sync-release-identity.py  (sync/check flow)
    - runtime/contract_compiler.py      (drift gate)
    - tests/test_trust_release_identity.py (parity assertions)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

# ── Valid surface type identifiers ──────────────────────────────────────────

SURFACE_TYPES = frozenset({
    "json_key_path",
    "regex_line",
    "yaml_line",
    "frontmatter_field",
    "changelog_header",
    "shell_literal",
    "js_literal",
    "banner_literal",
})


@dataclass(frozen=True)
class AuthoredSurface:
    """A version surface in an authored source file.

    Attributes:
        file_path: Relative path from repo root.
        surface_type: One of SURFACE_TYPES.
        field: For json_key_path — list of str/int keys to navigate.
               For regex_line/shell_literal/js_literal/banner_literal — regex pattern.
               For yaml_line/frontmatter_field — the YAML field name.
               For changelog_header — regex pattern matching the header.
        description: Human-readable description of this surface.
    """

    file_path: str
    surface_type: str
    field: Union[list[Union[str, int]], str]
    description: str = ""
    source_only: bool = False


# ── Explicit YAML bundle names (22 files) ──────────────────────────────────

_BUNDLE_NAMES: tuple[str, ...] = (
    "algorithms",
    "api-twin",
    "claim-judge",
    "control-plane",
    "data-lineage",
    "delta-classifier",
    "eval-gate",
    "health",
    "hook-governor",
    "incident-replay",
    "lsp-pack",
    "mcp-fabric",
    "plan-council",
    "preflight",
    "proof-gate",
    "remote-supervisor",
    "robotics",
    "secure-worktree-pipeline",
    "security-check",
    "test-intent-lock",
    "tracebank",
    "vision",
)


# ── Authored surfaces: explicit, no dynamic discovery ──────────────────────

AUTHORED_SURFACES: list[AuthoredSurface] = [
    # ── JSON key paths (10 fields across 7 files) ──
    AuthoredSurface(
        "package.json", "json_key_path", ["version"],
        "npm package version",
    ),
    AuthoredSurface(
        "settings.json", "json_key_path", ["_omg", "_version"],
        "OMG settings version",
    ),
    AuthoredSurface(
        "settings.json", "json_key_path", ["_omg", "generated", "contract_version"],
        "OMG generated contract version",
    ),
    AuthoredSurface(
        ".claude-plugin/plugin.json", "json_key_path", ["version"],
        "Claude plugin version",
    ),
    AuthoredSurface(
        ".claude-plugin/marketplace.json", "json_key_path", ["version"],
        "marketplace top-level version",
    ),
    AuthoredSurface(
        ".claude-plugin/marketplace.json", "json_key_path", ["metadata", "version"],
        "marketplace metadata version",
    ),
    AuthoredSurface(
        ".claude-plugin/marketplace.json", "json_key_path", ["plugins", 0, "version"],
        "marketplace plugins[0] version",
    ),
    AuthoredSurface(
        "plugins/core/plugin.json", "json_key_path", ["version"],
        "core plugin version",
    ),
    AuthoredSurface(
        "plugins/advanced/plugin.json", "json_key_path", ["version"],
        "advanced plugin version",
    ),
    AuthoredSurface(
        "registry/omg-capability.schema.json", "json_key_path", ["version"],
        "capability schema version",
    ),

    # ── Regex line (pyproject.toml) ──
    AuthoredSurface(
        "pyproject.toml", "regex_line", r'^version = "(.+?)"',
        "Python package version",
    ),

    # ── YAML bundles (22 files) ──
    *[
        AuthoredSurface(
            f"registry/bundles/{name}.yaml", "yaml_line", "version",
            f"{name} bundle version",
        )
        for name in _BUNDLE_NAMES
    ],

    # ── Changelog ──
    AuthoredSurface(
        "CHANGELOG.md", "changelog_header", r'^## \[?(\d+\.\d+\.\d+)\]?',
        "latest release header",
    ),

    # ── 6 previously missing authored surfaces ──

    # 1. OMG_COMPAT_CONTRACT.md — frontmatter version: field (line 3)
    AuthoredSurface(
        "OMG_COMPAT_CONTRACT.md", "frontmatter_field", "version",
        "compat contract frontmatter version",
    ),

    # 2. CLI-ADAPTER-MAP.md — 3 docs example version markers
    AuthoredSurface(
        "CLI-ADAPTER-MAP.md", "regex_line",
        r'^- \*\*Version:\*\* `(\d+\.\d+\.\d+)`',
        "docs example: version badge (line 165)",
    ),
    AuthoredSurface(
        "CLI-ADAPTER-MAP.md", "regex_line",
        r'^\s*"version":\s*"(\d+\.\d+\.\d+)"',
        "docs example: JSON version literal (line 209)",
    ),
    AuthoredSurface(
        "CLI-ADAPTER-MAP.md", "regex_line",
        r'^CANONICAL_VERSION\s*=\s*"(\d+\.\d+\.\d+)"',
        "docs example: Python constant (line 241)",
    ),

    # 3. OMG-setup.sh — VERSION="..." shell literal (line 8)
    AuthoredSurface(
        "OMG-setup.sh", "shell_literal", r'^VERSION="(.+?)"',
        "setup script version variable",
    ),

    # 4. hud/omg-hud.mjs — JS fallback literal (line 90)
    AuthoredSurface(
        "hud/omg-hud.mjs", "js_literal", r'return "(\d+\.\d+\.\d+)"',
        "HUD fallback version literal",
    ),

    # 5. .claude-plugin/scripts/install.sh — installer banner literal (line 22)
    AuthoredSurface(
        ".claude-plugin/scripts/install.sh", "banner_literal",
        r'v(\d+\.\d+\.\d+)',
        "installer banner version",
        source_only=True,
    ),

    # 6. runtime/omg_compat_contract_snapshot.json — contract_version field
    AuthoredSurface(
        "runtime/omg_compat_contract_snapshot.json", "json_key_path",
        ["contract_version"],
        "compat contract snapshot version",
    ),

    # 7. commands/OMG:validate.md — JSON example version field (line 39)
    AuthoredSurface(
        "commands/OMG:validate.md", "regex_line", r'^\s*"version":\s*"(\d+\.\d+\.\d+)"',
        "validate command JSON example version",
    ),

    # 8. settings.json — banner comment literal (line 3)
    AuthoredSurface(
        "settings.json", "banner_literal", r'OMG (\d+\.\d+\.\d+)',
        "settings banner comment version",
    ),
]


# ── Derived (generated) surface directories ────────────────────────────────
# These are validation-only targets — not authored, but must be checked for
# stale version residue after a bump.

DERIVED_SURFACE_DIRS: list[str] = [
    "dist/",
    "artifacts/release/",
    "build/lib/",
]


# ── Scoped residue targets ─────────────────────────────────────────────────
# Specific files/dirs inside generated trees where stale version residue
# must be rejected after a version bump.

SCOPED_RESIDUE_TARGETS: list[str] = [
    "dist/public/manifest.json",
    "dist/enterprise/manifest.json",
    "dist/public/bundle/",
    "dist/enterprise/bundle/",
    "artifacts/release/",
    "build/lib/",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_authored_paths() -> list[str]:
    """Return deduplicated list of file paths from AUTHORED_SURFACES.

    Preserves insertion order; useful for disk-existence checks.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for surface in AUTHORED_SURFACES:
        if surface.file_path not in seen:
            seen.add(surface.file_path)
            paths.append(surface.file_path)
    return paths


def get_derived_dirs() -> list[str]:
    """Return all generated directory paths."""
    return list(DERIVED_SURFACE_DIRS)


def surface_applies_to_root(surface: AuthoredSurface, root_dir: Path) -> bool:
    """Return whether a surface should be enforced for the given root layout."""
    if not surface.source_only:
        return True
    return (root_dir / ".git").exists()
