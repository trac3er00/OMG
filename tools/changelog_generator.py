#!/usr/bin/env python3
"""
Changelog Generator for OMG

Parses conventional commits from git log and generates/updates CHANGELOG.md
in Keep-a-Changelog format.

Feature flag: OMG_CHANGELOG_ENABLED (default: False)
"""

import os
import re
import sys
from datetime import date
from typing import Any, Dict, List, Optional

# Lazy imports
_git_inspector = None
_get_feature_flag = None


def _ensure_imports():
    """Lazy import git_inspector and feature flag helper."""
    global _git_inspector, _get_feature_flag
    if _git_inspector is None:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from tools import git_inspector as _gi
        from hooks._common import get_feature_flag as _gff
        _git_inspector = _gi
        _get_feature_flag = _gff


def _is_enabled() -> bool:
    """Check if changelog feature is enabled."""
    _ensure_imports()
    return _get_feature_flag("changelog", default=False)


# Supported conventional commit types
CONVENTIONAL_TYPES = frozenset({
    "feat", "fix", "docs", "style", "refactor",
    "test", "chore", "perf", "ci", "build", "sec",
})

# Regex for conventional commit: type(scope): description  OR  type: description
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<description>.+)$"
)

# Changelog section groupings
_TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
    "docs": "Changed",
    "style": "Changed",
    "build": "Changed",
    "ci": "Changed",
    "chore": "Other",
    "test": "Other",
    "sec": "Security",
}

_SECTION_ORDER = ["Added", "Fixed", "Changed", "Deprecated", "Removed", "Security", "Other"]


def parse_commit_log(cwd: str = ".") -> List[Dict[str, Any]]:
    """Parse git log for conventional commits.

    Args:
        cwd: Working directory (default: current directory)

    Returns:
        List of dicts with keys: type, scope, description, hash, author, date, breaking
        Returns empty list if OMG_CHANGELOG_ENABLED is False or no conventional commits found.
    """
    if not _is_enabled():
        return []

    _ensure_imports()
    raw_commits = _git_inspector.git_log(cwd, n=100)

    if not raw_commits:
        return []

    parsed = []
    for commit in raw_commits:
        subject = commit.get("subject", "").strip()
        if not subject:
            continue

        match = _CONVENTIONAL_RE.match(subject)
        if not match:
            continue

        commit_type = match.group("type").lower()
        if commit_type not in CONVENTIONAL_TYPES:
            continue

        # Detect breaking changes
        breaking = "BREAKING CHANGE" in subject or "!" in subject.split(":")[0]

        parsed.append({
            "type": commit_type,
            "scope": match.group("scope") or "",
            "description": match.group("description").strip(),
            "hash": commit.get("hash", "")[:7],
            "author": commit.get("author", ""),
            "date": commit.get("date", ""),
            "breaking": breaking,
        })

    return parsed


def generate_changelog_entry(
    commits: List[Dict[str, Any]],
    version: str = "Unreleased",
) -> str:
    """Format a Keep-a-Changelog section from parsed commits.

    Args:
        commits: List of parsed commit dicts from parse_commit_log()
        version: Version label (default: "Unreleased")

    Returns:
        Formatted changelog section string.
        Returns empty string if commits list is empty.
    """
    if not commits:
        return ""

    today = date.today().isoformat()
    header = f"## [{version}] - {today}"

    # Group commits by section
    sections: Dict[str, List[str]] = {s: [] for s in _SECTION_ORDER}

    for commit in commits:
        section = _TYPE_TO_SECTION.get(commit["type"], "Other")
        scope = commit.get("scope", "")
        description = commit["description"]
        short_hash = commit.get("hash", "")

        if scope:
            entry = f"- **{scope}**: {description}"
        else:
            entry = f"- {description}"

        if short_hash:
            entry += f" (#{short_hash})"

        if commit.get("breaking"):
            entry += " **[BREAKING]**"

        sections[section].append(entry)

    lines = [header, ""]

    for section_name in _SECTION_ORDER:
        entries = sections[section_name]
        if not entries:
            continue
        lines.append(f"### {section_name}")
        lines.extend(entries)
        lines.append("")

    # Strip trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def update_changelog(cwd: str = ".", version: str = None) -> bool:
    """Parse commits and prepend a new entry to CHANGELOG.md.

    Reads existing CHANGELOG.md (or creates a new one). Inserts the new
    entry after the top-level `# Changelog` header without overwriting
    existing sections.

    Args:
        cwd: Working directory (default: current directory)
        version: Version label (default: "Unreleased")

    Returns:
        True on success, False on failure or if no commits to add.
    """
    commits = parse_commit_log(cwd)
    if not commits:
        return False

    entry = generate_changelog_entry(commits, version=version or "Unreleased")
    if not entry:
        return False

    changelog_path = os.path.join(cwd, "CHANGELOG.md")

    try:
        if os.path.exists(changelog_path):
            with open(changelog_path, "r", encoding="utf-8") as f:
                existing = f.read()
        else:
            existing = "# Changelog\n\nAll notable changes to this project will be documented here.\n"

        # Find insertion point: after the first `# Changelog` header line
        lines = existing.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_idx = i + 1
                # Skip blank lines immediately after the header
                while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                    insert_idx += 1
                break

        new_block = entry + "\n\n"
        lines.insert(insert_idx, new_block)
        new_content = "".join(lines)

        with open(changelog_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return True

    except OSError:
        return False


def _dry_run(cwd: str = ".", version: str = None) -> str:
    """Return the changelog entry that would be written, without modifying any file."""
    commits = parse_commit_log(cwd)
    if not commits:
        return "[OMG Changelog] No conventional commits found (or feature flag disabled)."
    return generate_changelog_entry(commits, version=version or "Unreleased")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Changelog Generator — parses conventional commits and updates CHANGELOG.md"
    )
    parser.add_argument("--cwd", default=".", help="Working directory (default: .)")
    parser.add_argument("--version", default=None, help="Version label (default: Unreleased)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the changelog entry without writing to file",
    )
    args = parser.parse_args()

    if args.dry_run:
        print(_dry_run(cwd=args.cwd, version=args.version))
        return

    success = update_changelog(cwd=args.cwd, version=args.version)
    if success:
        print("[OMG Changelog] CHANGELOG.md updated successfully.")
    else:
        print("[OMG Changelog] No changes written (no commits or feature flag disabled).")
        sys.exit(1)


_SYNTH_TYPE_TO_SECTION = {
    "feat": "Features",
    "fix": "Bug Fixes",
}

_SYNTH_SECTION_ORDER = ["Features", "Bug Fixes", "Breaking Changes", "Other"]


def synthesize_changelog(commits: List[Dict[str, Any]]) -> str:
    """Public API: group raw commit dicts by type into markdown sections.

    Accepts dicts with ``message`` (str), optional ``hash`` and ``files``.
    """
    if not commits:
        return ""

    sections: Dict[str, List[str]] = {s: [] for s in _SYNTH_SECTION_ORDER}

    for commit in commits:
        message = commit.get("message", "").strip()
        if not message:
            continue

        is_breaking = message.startswith("BREAKING CHANGE")
        if not is_breaking:
            colon_idx = message.find(":")
            if colon_idx > 0 and "!" in message[:colon_idx]:
                is_breaking = True

        if is_breaking:
            sections["Breaking Changes"].append(f"- {message}")
            continue

        match = _CONVENTIONAL_RE.match(message)
        if match:
            commit_type = match.group("type").lower()
            section = _SYNTH_TYPE_TO_SECTION.get(commit_type, "Other")
            sections[section].append(f"- {message}")
        else:
            sections["Other"].append(f"- {message}")

    lines: List[str] = ["## Changes", ""]

    for section_name in _SYNTH_SECTION_ORDER:
        entries = sections[section_name]
        if not entries:
            continue
        lines.append(f"### {section_name}")
        lines.extend(entries)
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


def write_changelog(
    commits: List[Dict[str, Any]],
    output_path: Optional[str] = None,
) -> str:
    """Synthesize changelog; write to *output_path* when given, else return string."""
    content = synthesize_changelog(commits)
    if not content:
        return ""

    if output_path is not None:
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    return content


if __name__ == "__main__":
    main()
