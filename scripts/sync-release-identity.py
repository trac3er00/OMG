#!/usr/bin/env python3
"""Sync/check flow for tracked source identity surfaces.

Reads CANONICAL_VERSION from runtime/adoption.py via AST and updates
or validates all tracked source surfaces.

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

KeyPath = list[Union[str, int]]


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


JSON_SURFACES: list[tuple[str, list[KeyPath]]] = [
    ("package.json", [["version"]]),
    ("settings.json", [
        ["_omg", "_version"],
        ["_omg", "generated", "contract_version"],
    ]),
    (".claude-plugin/plugin.json", [["version"]]),
    (".claude-plugin/marketplace.json", [
        ["version"],
        ["metadata", "version"],
        ["plugins", 0, "version"],
    ]),
    ("plugins/core/plugin.json", [["version"]]),
    ("plugins/advanced/plugin.json", [["version"]]),
    ("registry/omg-capability.schema.json", [["version"]]),
]

REGEX_SURFACES: list[tuple[str, str, str]] = [
    (
        "pyproject.toml",
        r'^version = "(.+?)"',
        'version = "{version}"',
    ),
]

YAML_BUNDLE_DIR = "registry/bundles"
CHANGELOG_FILE = "CHANGELOG.md"


def check_json_surfaces(
    repo_root: Path, canonical: str,
) -> list[tuple[str, str | None]]:
    drifts: list[tuple[str, str | None]] = []
    for file_rel, key_paths in JSON_SURFACES:
        file_path = repo_root / file_rel
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            for kp in key_paths:
                surface = f"{file_rel} {_format_key_path(kp)}"
                drifts.append((surface, f"<error: {e}>"))
            continue

        for kp in key_paths:
            surface = f"{file_rel} {_format_key_path(kp)}"
            current = _get_nested(data, kp)
            if current != canonical:
                drifts.append((
                    surface,
                    str(current) if current is not None else None,
                ))
    return drifts


def check_regex_surfaces(
    repo_root: Path, canonical: str,
) -> list[tuple[str, str | None]]:
    drifts: list[tuple[str, str | None]] = []
    for file_rel, pattern, _repl in REGEX_SURFACES:
        file_path = repo_root / file_rel
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as e:
            drifts.append((file_rel, f"<error: {e}>"))
            continue

        match = re.search(pattern, content, re.MULTILINE)
        if match:
            current = match.group(1)
            if current != canonical:
                drifts.append((file_rel, current))
        else:
            drifts.append((file_rel, "<pattern not found>"))
    return drifts


def check_yaml_bundles(
    repo_root: Path, canonical: str,
) -> list[tuple[str, str | None]]:
    drifts: list[tuple[str, str | None]] = []
    bundle_dir = repo_root / YAML_BUNDLE_DIR
    if not bundle_dir.is_dir():
        drifts.append((YAML_BUNDLE_DIR, "<directory not found>"))
        return drifts

    for yaml_file in sorted(bundle_dir.glob("*.yaml")):
        rel = str(yaml_file.relative_to(repo_root))
        try:
            content = yaml_file.read_text(encoding="utf-8")
        except OSError as e:
            drifts.append((rel, f"<error: {e}>"))
            continue

        match = re.search(r"^version:\s+(.+)$", content, re.MULTILINE)
        if match:
            current = match.group(1).strip()
            if current != canonical:
                drifts.append((rel, current))
        else:
            drifts.append((rel, "<pattern not found>"))
    return drifts


def check_changelog(
    repo_root: Path, canonical: str,
) -> list[tuple[str, str | None]]:
    drifts: list[tuple[str, str | None]] = []
    changelog = repo_root / CHANGELOG_FILE
    try:
        content = changelog.read_text(encoding="utf-8")
    except OSError as e:
        drifts.append((CHANGELOG_FILE, f"<error: {e}>"))
        return drifts

    # Pattern: ^## [?X.Y.Z]? — handles both ## 2.1.1 and ## [2.1.1] formats
    match = re.search(
        r"^## \[?(\d+\.\d+\.\d+)\]?", content, re.MULTILINE,
    )
    if match:
        current = match.group(1)
        if current != canonical:
            drifts.append((CHANGELOG_FILE, current))
    else:
        drifts.append((CHANGELOG_FILE, "<no version header found>"))
    return drifts


def update_json_surfaces(repo_root: Path, canonical: str) -> list[str]:
    updated: list[str] = []
    for file_rel, key_paths in JSON_SURFACES:
        file_path = repo_root / file_rel
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  WARNING: Could not read {file_rel}: {e}", file=sys.stderr)
            continue

        file_changed = False
        for kp in key_paths:
            surface = f"{file_rel} {_format_key_path(kp)}"
            current = _get_nested(data, kp)
            if current != canonical:
                _set_nested(data, kp, canonical)
                updated.append(surface)
                file_changed = True

        if file_changed:
            file_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return updated


def update_regex_surfaces(repo_root: Path, canonical: str) -> list[str]:
    updated: list[str] = []
    for file_rel, pattern, repl_template in REGEX_SURFACES:
        file_path = repo_root / file_rel
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  WARNING: Could not read {file_rel}: {e}", file=sys.stderr)
            continue

        replacement = repl_template.format(version=canonical)
        new_content, count = re.subn(
            pattern, replacement, content, count=1, flags=re.MULTILINE,
        )
        if count > 0 and new_content != content:
            file_path.write_text(new_content, encoding="utf-8")
            updated.append(file_rel)
    return updated


def update_yaml_bundles(repo_root: Path, canonical: str) -> list[str]:
    updated: list[str] = []
    bundle_dir = repo_root / YAML_BUNDLE_DIR
    if not bundle_dir.is_dir():
        print(
            f"  WARNING: {YAML_BUNDLE_DIR} not found", file=sys.stderr,
        )
        return updated

    replacement = f"version: {canonical}"
    for yaml_file in sorted(bundle_dir.glob("*.yaml")):
        rel = str(yaml_file.relative_to(repo_root))
        try:
            content = yaml_file.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  WARNING: Could not read {rel}: {e}", file=sys.stderr)
            continue

        new_content, count = re.subn(
            r"^version: .*$", replacement, content,
            count=1, flags=re.MULTILINE,
        )
        if count > 0 and new_content != content:
            yaml_file.write_text(new_content, encoding="utf-8")
            updated.append(rel)
    return updated


def update_changelog(repo_root: Path, canonical: str) -> list[str]:
    updated: list[str] = []
    changelog = repo_root / CHANGELOG_FILE
    try:
        content = changelog.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: Could not read {CHANGELOG_FILE}: {e}", file=sys.stderr)
        return updated

    # Pattern preserves bracket style ([X.Y.Z] vs X.Y.Z) and date suffix
    def _replace_version(m: re.Match[str]) -> str:
        return f"{m.group(1)}{canonical}{m.group(3)}"

    new_content, count = re.subn(
        r"^(## \[?)(\d+\.\d+\.\d+)(\]?.*)",
        _replace_version, content, count=1, flags=re.MULTILINE,
    )
    if count > 0 and new_content != content:
        changelog.write_text(new_content, encoding="utf-8")
        updated.append(CHANGELOG_FILE)
    return updated


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
        all_drifts.extend(check_json_surfaces(repo_root, canonical))
        all_drifts.extend(check_regex_surfaces(repo_root, canonical))
        all_drifts.extend(check_yaml_bundles(repo_root, canonical))
        all_drifts.extend(check_changelog(repo_root, canonical))

        if all_drifts:
            print(f"\nDrift detected in {len(all_drifts)} surface(s):\n")
            for surface, current in all_drifts:
                cur = current if current is not None else "<not found>"
                print(f"  DRIFT  {surface}: {cur} (expected {canonical})")
            return 1
        else:
            print("\nAll tracked surfaces in sync.")
            return 0
    else:
        all_updated: list[str] = []
        all_updated.extend(update_json_surfaces(repo_root, canonical))
        all_updated.extend(update_regex_surfaces(repo_root, canonical))
        all_updated.extend(update_yaml_bundles(repo_root, canonical))
        all_updated.extend(update_changelog(repo_root, canonical))

        if all_updated:
            print(f"\nUpdated {len(all_updated)} surface(s):\n")
            for u in all_updated:
                print(f"  UPDATED  {u}")
        else:
            print("\nAll tracked surfaces already at canonical version.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
