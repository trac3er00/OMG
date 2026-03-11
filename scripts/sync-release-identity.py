#!/usr/bin/env python3
"""Sync/check flow for tracked source identity surfaces.

Reads CANONICAL_VERSION from runtime/adoption.py via AST and updates
or validates all tracked source surfaces defined in runtime/release_surfaces.py.

Usage:
    python3 scripts/sync-release-identity.py          # write mode (default)
    python3 scripts/sync-release-identity.py --check   # check mode (exits non-zero on drift)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Union, cast

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from runtime.release_surfaces import (
    AUTHORED_SURFACES,
    DERIVED_SURFACE_DIRS,
    AuthoredSurface,
    surface_applies_to_root,
)

KeyPath = list[Union[str, int]]

# Derived directories that must never be mutated
_DERIVED_DIRS = frozenset(DERIVED_SURFACE_DIRS)


# ── Version extraction (AST-based, zero-dependency) ────────────────────────


def extract_canonical_version(source_file: Path) -> str | None:
    try:
        source_code = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error reading {source_file}: {e}", file=sys.stderr)
        return None

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"Syntax error in {source_file}: {e}", file=sys.stderr)
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                    if isinstance(node.value, ast.Constant):
                        val = node.value.value
                        if isinstance(val, str):
                            return cast(str, val)
                    elif isinstance(node.value, ast.Str):  # Python 3.7 compat
                        return cast(str, node.value.s)

    return None


# ── JSON helpers ────────────────────────────────────────────────────────────


def _get_nested(data: Any, key_path: KeyPath) -> Any:
    current = data
    for key in key_path:
        if isinstance(current, dict) and isinstance(key, str):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            if 0 <= key < len(current):
                current = current[key]
            else:
                return None
        else:
            return None
        if current is None:
            return None
    return current


def _set_nested(data: Any, key_path: KeyPath, value: Any) -> None:
    current = data
    for key in key_path[:-1]:
        if isinstance(current, dict) and isinstance(key, str):
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int):
            current = current[key]
    last = key_path[-1]
    if isinstance(current, dict) and isinstance(last, str):
        current[last] = value
    elif isinstance(current, list) and isinstance(last, int):
        current[last] = value


def _format_key_path(kp: KeyPath) -> str:
    parts: list[str] = []
    for k in kp:
        if isinstance(k, int):
            parts.append(f"[{k}]")
        else:
            if parts:
                parts.append(f".{k}")
            else:
                parts.append(k)
    return "".join(parts)


# ── Guard ───────────────────────────────────────────────────────────────────


def _guard_derived(surface: AuthoredSurface) -> None:
    """Raise if surface targets a derived/generated directory."""
    for d in _DERIVED_DIRS:
        if surface.file_path.startswith(d):
            raise ValueError(
                f"Refusing to mutate derived directory: {surface.file_path}"
            )


def _surface_label(surface: AuthoredSurface) -> str:
    """Human-readable label for a surface."""
    if surface.surface_type == "json_key_path" and isinstance(surface.field, list):
        return f"{surface.file_path} {_format_key_path(surface.field)}"
    return surface.file_path


def _replace_group1(m: re.Match[str], new_version: str) -> str:
    """Replace captured group 1 in a regex match, preserving surrounding text."""
    prefix = m.group(0)[: m.start(1) - m.start(0)]
    suffix = m.group(0)[m.end(1) - m.start(0) :]
    return prefix + new_version + suffix


# ── Check handlers ──────────────────────────────────────────────────────────


def _check_json_key_path(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    label = _surface_label(surface)
    file_path = repo_root / surface.file_path
    key_path = cast(KeyPath, surface.field)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [(label, f"<error: {e}>")]
    current = _get_nested(data, key_path)
    if current != canonical:
        return [(label, str(current) if current is not None else None)]
    return []


def _check_regex(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    """Generic check for regex_line, shell_literal, js_literal, banner_literal."""
    label = _surface_label(surface)
    pattern = cast(str, surface.field)
    try:
        content = (repo_root / surface.file_path).read_text(encoding="utf-8")
    except OSError as e:
        return [(label, f"<error: {e}>")]
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        current = match.group(1)
        if current != canonical:
            return [(label, current)]
        return []
    return [(label, "<pattern not found>")]


def _check_yaml_line(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    label = _surface_label(surface)
    try:
        content = (repo_root / surface.file_path).read_text(encoding="utf-8")
    except OSError as e:
        return [(label, f"<error: {e}>")]
    match = re.search(r"^version:\s+(.+)$", content, re.MULTILINE)
    if match:
        current = match.group(1).strip()
        if current != canonical:
            return [(label, current)]
        return []
    return [(label, "<pattern not found>")]


def _check_frontmatter_field(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    label = _surface_label(surface)
    field_name = cast(str, surface.field)
    try:
        content = (repo_root / surface.file_path).read_text(encoding="utf-8")
    except OSError as e:
        return [(label, f"<error: {e}>")]
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return [(label, "<no frontmatter found>")]
    field_match = re.search(
        rf"^{re.escape(field_name)}:\s+(.+)$", fm_match.group(1), re.MULTILINE,
    )
    if field_match:
        current = field_match.group(1).strip()
        if current != canonical:
            return [(label, current)]
        return []
    return [(label, f"<field '{field_name}' not found in frontmatter>")]


def _check_changelog_header(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    label = _surface_label(surface)
    pattern = cast(str, surface.field)
    try:
        content = (repo_root / surface.file_path).read_text(encoding="utf-8")
    except OSError as e:
        return [(label, f"<error: {e}>")]
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        current = match.group(1)
        if current != canonical:
            return [(label, current)]
        return []
    return [(label, "<no version header found>")]


# ── Update handlers ─────────────────────────────────────────────────────────


def _update_json_key_path(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    label = _surface_label(surface)
    file_path = repo_root / surface.file_path
    key_path = cast(KeyPath, surface.field)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  WARNING: Could not read {surface.file_path}: {e}", file=sys.stderr)
        return []
    current = _get_nested(data, key_path)
    if current != canonical:
        _set_nested(data, key_path, canonical)
        file_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return [label]
    return []


def _update_regex(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    """Generic update for regex_line, shell_literal, js_literal, banner_literal."""
    label = _surface_label(surface)
    pattern = cast(str, surface.field)
    file_path = repo_root / surface.file_path
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: Could not read {surface.file_path}: {e}", file=sys.stderr)
        return []
    new_content = re.sub(
        pattern,
        lambda m: _replace_group1(m, canonical),
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        return [label]
    return []


def _update_yaml_line(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    label = _surface_label(surface)
    file_path = repo_root / surface.file_path
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: Could not read {surface.file_path}: {e}", file=sys.stderr)
        return []
    replacement = f"version: {canonical}"
    new_content, count = re.subn(
        r"^version: .*$", replacement, content, count=1, flags=re.MULTILINE,
    )
    if count > 0 and new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        return [label]
    return []


def _update_frontmatter_field(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    label = _surface_label(surface)
    file_path = repo_root / surface.file_path
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: Could not read {surface.file_path}: {e}", file=sys.stderr)
        return []
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        print(f"  WARNING: No frontmatter in {surface.file_path}", file=sys.stderr)
        return []
    field_name = cast(str, surface.field)
    old_fm = fm_match.group(1)
    new_fm = re.sub(
        rf"^({re.escape(field_name)}:\s+)(.+)$",
        rf"\g<1>{canonical}",
        old_fm,
        count=1,
        flags=re.MULTILINE,
    )
    if new_fm != old_fm:
        new_content = content[: fm_match.start(1)] + new_fm + content[fm_match.end(1) :]
        file_path.write_text(new_content, encoding="utf-8")
        return [label]
    return []


def _update_changelog_header(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    label = _surface_label(surface)
    file_path = repo_root / surface.file_path
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: Could not read {surface.file_path}: {e}", file=sys.stderr)
        return []

    def _replace_version(m: re.Match[str]) -> str:
        return f"{m.group(1)}{canonical}{m.group(3)}"

    new_content, count = re.subn(
        r"^(## \[?)(\d+\.\d+\.\d+)(\]?.*)",
        _replace_version,
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count > 0 and new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        return [label]
    return []


# ── Dispatch tables ─────────────────────────────────────────────────────────

_CHECK_DISPATCH = {
    "json_key_path": _check_json_key_path,
    "regex_line": _check_regex,
    "yaml_line": _check_yaml_line,
    "frontmatter_field": _check_frontmatter_field,
    "changelog_header": _check_changelog_header,
    "shell_literal": _check_regex,
    "js_literal": _check_regex,
    "banner_literal": _check_regex,
}

_UPDATE_DISPATCH = {
    "json_key_path": _update_json_key_path,
    "regex_line": _update_regex,
    "yaml_line": _update_yaml_line,
    "frontmatter_field": _update_frontmatter_field,
    "changelog_header": _update_changelog_header,
    "shell_literal": _update_regex,
    "js_literal": _update_regex,
    "banner_literal": _update_regex,
}


# ── Public API ──────────────────────────────────────────────────────────────


def check_surface(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[tuple[str, str | None]]:
    """Check a single surface for version drift."""
    if not surface_applies_to_root(surface, repo_root):
        return []
    _guard_derived(surface)
    handler = _CHECK_DISPATCH.get(surface.surface_type)
    if handler is None:
        return [(_surface_label(surface), f"<unknown type: {surface.surface_type}>")]
    return handler(repo_root, surface, canonical)


def update_surface(
    repo_root: Path, surface: AuthoredSurface, canonical: str,
) -> list[str]:
    """Update a single surface to canonical version."""
    if not surface_applies_to_root(surface, repo_root):
        return []
    _guard_derived(surface)
    handler = _UPDATE_DISPATCH.get(surface.surface_type)
    if handler is None:
        return []
    return handler(repo_root, surface, canonical)


# ── CLI entry point ─────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync or check tracked source identity surfaces.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: exit non-zero if any surface drifts",
    )
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent
    adoption_file = repo_root / "runtime" / "adoption.py"

    if not adoption_file.exists():
        repo_root = Path.cwd()
        adoption_file = repo_root / "runtime" / "adoption.py"

    if not adoption_file.exists():
        print(f"Error: {adoption_file} not found", file=sys.stderr)
        return 1

    canonical = extract_canonical_version(adoption_file)
    if canonical is None:
        print("Error: CANONICAL_VERSION not found", file=sys.stderr)
        return 1

    print(f"Canonical version: {canonical}")

    if args.check:
        all_drifts: list[tuple[str, str | None]] = []
        for surface in AUTHORED_SURFACES:
            all_drifts.extend(check_surface(repo_root, surface, canonical))

        if all_drifts:
            print(f"\nDrift detected in {len(all_drifts)} surface(s):\n")
            for surf, current in all_drifts:
                cur = current if current is not None else "<not found>"
                print(f"  DRIFT  {surf}: {cur} (expected {canonical})")
            return 1
        else:
            print("\nAll tracked surfaces in sync.")
            return 0
    else:
        all_updated: list[str] = []
        for surface in AUTHORED_SURFACES:
            all_updated.extend(update_surface(repo_root, surface, canonical))

        if all_updated:
            print(f"\nUpdated {len(all_updated)} surface(s):\n")
            for u in all_updated:
                print(f"  UPDATED  {u}")
        else:
            print("\nAll tracked surfaces already at canonical version.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
