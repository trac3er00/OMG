#!/usr/bin/env python3
"""
AI Commit Splitter for OMG

Analyzes git changes and groups them into logical atomic commits
with hunk-level staging support. Read-only analysis — never runs git commit.

Feature flag: OMG_AI_COMMIT_ENABLED (default: False)
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

# Lazy imports for git_inspector and feature flags
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
    """Check if AI commit splitter feature is enabled."""
    _ensure_imports()
    return _get_feature_flag("ai_commit", default=False)


# --- File Classification ---

# Extension → category mapping
_EXT_CATEGORY = {
    # Python
    ".py": "python",
    ".pyi": "python",
    ".pyx": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # Config
    ".json": "config",
    ".yaml": "config",
    ".yml": "config",
    ".toml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".env": "config",
    ".conf": "config",
    ".properties": "config",
    # Docs
    ".md": "docs",
    ".rst": "docs",
    ".txt": "docs",
    ".adoc": "docs",
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    # CSS/Styles
    ".css": "styles",
    ".scss": "styles",
    ".less": "styles",
    ".sass": "styles",
    # HTML/Templates
    ".html": "markup",
    ".htm": "markup",
    ".xml": "markup",
    ".svg": "markup",
}

# Test path indicators
_TEST_INDICATORS = (
    "test_",
    "_test.",
    "tests/",
    "test/",
    "__tests__/",
    ".test.",
    ".spec.",
    "spec/",
    "conftest.py",
)

# Category → default suggested commit type
_CATEGORY_DEFAULT_TYPE = {
    "python": "feat",
    "javascript": "feat",
    "shell": "chore",
    "config": "chore",
    "docs": "docs",
    "styles": "style",
    "markup": "feat",
    "tests": "test",
    "other": "chore",
}


def _classify_file(file_path: str) -> str:
    """Classify a file path into a category.

    Test files are always classified as 'tests' regardless of extension.

    Args:
        file_path: Relative file path from git diff.

    Returns:
        Category string: 'python', 'javascript', 'config', 'docs',
        'tests', 'shell', 'styles', 'markup', or 'other'.
    """
    if file_path is None:
        return "other"

    lower_path = file_path.lower()

    # Check for test files first — they always get their own group
    for indicator in _TEST_INDICATORS:
        if indicator in lower_path:
            return "tests"

    # Classify by extension
    _, ext = os.path.splitext(lower_path)
    return _EXT_CATEGORY.get(ext, "other")


def _derive_scope(files: List[str]) -> str:
    """Derive a scope name from a list of files.

    Uses the most common parent directory or module name.

    Args:
        files: List of file paths.

    Returns:
        Scope string suitable for conventional commit format.
    """
    if not files:
        return "general"

    # Collect directory components
    dirs: List[str] = []
    for f in files:
        parts = f.replace("\\", "/").split("/")
        if len(parts) > 1:
            dirs.append(parts[0])
        else:
            # Single file at root — use filename without extension
            name, _ = os.path.splitext(parts[0])
            dirs.append(name)

    if not dirs:
        return "general"

    # Most common directory
    from collections import Counter
    counts = Counter(dirs)
    scope = counts.most_common(1)[0][0]
    return scope


def _derive_description(category: str, files: List[str]) -> str:
    """Generate a short description for a commit group.

    Args:
        category: File category (e.g., 'python', 'tests').
        files: List of affected files.

    Returns:
        Human-readable description string.
    """
    n = len(files)
    if category == "tests":
        if n == 1:
            return f"update test {os.path.basename(files[0])}"
        return f"update {n} test files"
    if category == "docs":
        if n == 1:
            return f"update {os.path.basename(files[0])}"
        return f"update {n} documentation files"
    if category == "config":
        if n == 1:
            return f"update {os.path.basename(files[0])}"
        return f"update {n} config files"
    # Source code
    if n == 1:
        return f"update {os.path.basename(files[0])}"
    return f"update {n} {category} files"


# --- Public API ---


def analyze_changes(cwd: str = ".") -> List[Dict[str, Any]]:
    """Analyze git changes and group hunks by logical concern.

    Groups changes by file type/category, always separating test files
    from source code. Returns an empty list when the feature flag
    ``OMG_AI_COMMIT_ENABLED`` is ``False``.

    Args:
        cwd: Working directory (default: current directory).

    Returns:
        List of dicts, each with keys:
            - group_name (str): Human-readable group name.
            - files (list[str]): Affected file paths.
            - hunks (list[dict]): Raw hunk dicts from git_hunk().
            - suggested_type (str): Conventional commit type.
    """
    if not _is_enabled():
        return []

    _ensure_imports()
    hunks = _git_inspector.git_hunk(cwd)

    if not hunks:
        return []

    # Bucket hunks by category
    buckets: Dict[str, Dict[str, Any]] = {}
    for hunk in hunks:
        file_path = hunk.get("file", "")
        category = _classify_file(file_path)

        if category not in buckets:
            buckets[category] = {
                "files_set": set(),
                "hunks": [],
            }
        buckets[category]["files_set"].add(file_path)
        buckets[category]["hunks"].append(hunk)

    # Build result groups
    groups: List[Dict[str, Any]] = []
    for category, data in sorted(buckets.items()):
        files = sorted(data["files_set"])
        groups.append({
            "group_name": category,
            "files": files,
            "hunks": data["hunks"],
            "suggested_type": _CATEGORY_DEFAULT_TYPE.get(category, "chore"),
        })

    return groups


def generate_commit_plan(cwd: str = ".") -> Dict[str, Any]:
    """Generate a full commit plan with proposed messages.

    Calls ``analyze_changes()`` and builds conventional commit messages
    for each group. Returns an empty plan when the feature flag is off.

    Args:
        cwd: Working directory (default: current directory).

    Returns:
        Dict with keys:
            - groups (list[dict]): Raw groups from analyze_changes().
            - proposed_commits (list[dict]): Each with ``message``,
              ``files``, and ``hunks``.
            - total_commits (int): Number of proposed commits.
    """
    groups = analyze_changes(cwd)

    if not groups:
        return {
            "groups": [],
            "proposed_commits": [],
            "total_commits": 0,
        }

    proposed: List[Dict[str, Any]] = []
    for group in groups:
        commit_type = group["suggested_type"]
        scope = _derive_scope(group["files"])
        description = _derive_description(group["group_name"], group["files"])
        message = f"{commit_type}({scope}): {description}"

        proposed.append({
            "message": message,
            "files": group["files"],
            "hunks": group["hunks"],
        })

    return {
        "groups": groups,
        "proposed_commits": proposed,
        "total_commits": len(proposed),
    }


def preview_commit_plan(cwd: str = ".") -> str:
    """Human-readable preview of the commit plan.

    Args:
        cwd: Working directory (default: current directory).

    Returns:
        Formatted string showing each proposed commit and affected files.
        Returns a notice string if the feature flag is off or no changes found.
    """
    plan = generate_commit_plan(cwd)

    if plan["total_commits"] == 0:
        if not _is_enabled():
            return "[OMG] AI Commit Splitter is disabled. Set OMG_AI_COMMIT_ENABLED=1 to enable."
        return "[OMG] No uncommitted changes found."

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  OMG AI Commit Splitter — Proposed Commit Plan")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Total proposed commits: {plan['total_commits']}")
    lines.append("")

    for idx, commit in enumerate(plan["proposed_commits"], 1):
        lines.append(f"  Commit {idx}: {commit['message']}")
        lines.append(f"  {'─' * 50}")
        for f in commit["files"]:
            lines.append(f"    • {f}")
        hunk_count = len(commit["hunks"])
        lines.append(f"    ({hunk_count} hunk{'s' if hunk_count != 1 else ''})")
        lines.append("")

    lines.append("=" * 60)
    lines.append("  NOTE: This is a preview only. No commits were made.")
    lines.append("=" * 60)

    return "\n".join(lines)


# --- CLI ---


def main():
    """CLI entry point."""
    if len(sys.argv) < 2 or sys.argv[1] != "--dry-run":
        print("Usage:", file=sys.stderr)
        print("  python3 tools/commit_splitter.py --dry-run", file=sys.stderr)
        sys.exit(1)

    cwd = os.getcwd()
    output = preview_commit_plan(cwd)
    print(output)


if __name__ == "__main__":
    main()
