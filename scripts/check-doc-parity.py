#!/usr/bin/env python3
"""
OMG Doc-Parity Checker

Verifies documentation matches actual repo state:
- Workflow badges point to existing workflows
- Version strings in install docs match package.json
- No references to deleted workflows (except in CONTRIBUTING.md "removed" section)
- Plugin commands have corresponding .md files
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DELETED_WORKFLOWS = [
    "omg-compat-gate.yml",
    "evidence-gate.yml",
    "omg-release-readiness.yml",
    "omg-artifact-self-audit.yml",
    "action.yml",
]


def check_workflow_badges() -> list[str]:
    """Check that workflow badge URLs reference existing workflows."""
    errors = []
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    existing_workflows = {f.name for f in workflows_dir.glob("*.yml")} if workflows_dir.exists() else set()

    badge_pattern = re.compile(r"actions/workflows/([a-zA-Z0-9_-]+\.yml)/badge\.svg")
    docs_to_check = [REPO_ROOT / "README.md", REPO_ROOT / "docs" / "proof.md"]

    for doc_path in docs_to_check:
        if not doc_path.exists():
            continue
        content = doc_path.read_text()
        for match in badge_pattern.finditer(content):
            workflow_name = match.group(1)
            if workflow_name not in existing_workflows:
                errors.append(f"{doc_path.relative_to(REPO_ROOT)}: badge references non-existent workflow '{workflow_name}'")

    return errors


def check_version_strings() -> list[str]:
    """Check install docs for outdated version strings."""
    warnings = []
    pkg_json = REPO_ROOT / "package.json"
    if not pkg_json.exists():
        return ["package.json not found"]

    current_version = json.loads(pkg_json.read_text()).get("version", "")
    if not current_version:
        return ["package.json has no version field"]

    version_pattern = re.compile(r"\bv?(\d+\.\d+\.\d+)\b")
    install_dir = REPO_ROOT / "docs" / "install"

    if not install_dir.exists():
        return []

    for md_file in install_dir.glob("*.md"):
        content = md_file.read_text()
        for match in version_pattern.finditer(content):
            found_version = match.group(1)
            if found_version != current_version and _is_older_version(found_version, current_version):
                warnings.append(f"{md_file.relative_to(REPO_ROOT)}: references older version '{found_version}' (current: {current_version})")

    return warnings


def _is_older_version(v1: str, v2: str) -> bool:
    """Return True if v1 is older than v2."""
    try:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        return parts1 < parts2
    except ValueError:
        return False


def check_deleted_workflow_references() -> list[str]:
    """Check for references to deleted workflows outside allowed sections."""
    errors = []
    files_to_check: list[Path] = []

    for pattern in ["*.md", "*.py"]:
        files_to_check.extend(REPO_ROOT.rglob(pattern))

    for file_path in files_to_check:
        if ".venv" in str(file_path) or "node_modules" in str(file_path):
            continue
        if not file_path.is_file():
            continue

        try:
            content = file_path.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = file_path.relative_to(REPO_ROOT)
        is_contributing = rel_path.name == "CONTRIBUTING.md"

        for workflow in DELETED_WORKFLOWS:
            if workflow not in content:
                continue

            if is_contributing:
                removed_section_match = re.search(
                    r"###\s*Legacy CI gates \(removed\).*?(?=^##|\Z)", content, re.MULTILINE | re.DOTALL
                )
                if removed_section_match:
                    removed_section = removed_section_match.group(0)
                    content_outside_removed = content.replace(removed_section, "")
                    if workflow in content_outside_removed:
                        errors.append(f"{rel_path}: references deleted workflow '{workflow}' outside 'removed' section")
                else:
                    errors.append(f"{rel_path}: references deleted workflow '{workflow}' (no 'removed' section found)")
            else:
                errors.append(f"{rel_path}: references deleted workflow '{workflow}'")

    return errors


def check_command_registration() -> list[str]:
    """Verify plugin commands have corresponding .md files."""
    errors = []

    plugin_configs = [
        (REPO_ROOT / "plugins" / "core" / "plugin.json", REPO_ROOT / "commands"),
        (REPO_ROOT / "plugins" / "advanced" / "plugin.json", REPO_ROOT / "plugins" / "advanced" / "commands"),
    ]

    for plugin_json, commands_dir in plugin_configs:
        if not plugin_json.exists():
            errors.append(f"{plugin_json.relative_to(REPO_ROOT)}: plugin.json not found")
            continue

        try:
            config = json.loads(plugin_json.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{plugin_json.relative_to(REPO_ROOT)}: invalid JSON - {e}")
            continue

        commands = config.get("commands", {})
        for cmd_name, cmd_config in commands.items():
            cmd_path = cmd_config.get("path", "")
            if not cmd_path:
                errors.append(f"{plugin_json.relative_to(REPO_ROOT)}: command '{cmd_name}' has no path")
                continue

            expected_file = commands_dir / Path(cmd_path).name
            if not expected_file.exists():
                errors.append(f"{plugin_json.relative_to(REPO_ROOT)}: command '{cmd_name}' references missing file '{expected_file.relative_to(REPO_ROOT)}'")

    return errors


def main() -> int:
    print("OMG Doc-Parity Check")
    print("=" * 40)

    all_passed = True

    # Check 1: Workflow badges
    print("\n[1/4] Checking workflow badges...")
    badge_errors = check_workflow_badges()
    if badge_errors:
        all_passed = False
        for err in badge_errors:
            print(f"  FAIL: {err}")
    else:
        print("  PASS: All workflow badges reference existing workflows")

    # Check 2: Version strings
    print("\n[2/4] Checking version strings...")
    version_warnings = check_version_strings()
    if version_warnings:
        for warn in version_warnings:
            print(f"  WARN: {warn}")
    else:
        print("  PASS: No outdated version strings found")

    # Check 3: Deleted workflow references
    print("\n[3/4] Checking for deleted workflow references...")
    deleted_errors = check_deleted_workflow_references()
    if deleted_errors:
        all_passed = False
        for err in deleted_errors:
            print(f"  FAIL: {err}")
    else:
        print("  PASS: No invalid references to deleted workflows")

    # Check 4: Command registration
    print("\n[4/4] Checking command registration...")
    cmd_errors = check_command_registration()
    if cmd_errors:
        all_passed = False
        for err in cmd_errors:
            print(f"  FAIL: {err}")
    else:
        print("  PASS: All plugin commands have corresponding .md files")

    print("\n" + "=" * 40)
    if all_passed:
        print("Result: ALL CHECKS PASSED")
        return 0
    else:
        print("Result: SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
