#!/usr/bin/env python3
"""
PR Description Generator for OMG

Generates structured pull request descriptions from branch name,
commit history, and diff statistics. Output-only tool — never
invokes `gh pr create` or modifies git state.

No feature flag required (documentation output, not a hook).
"""

import os
import re
from typing import Any, Dict, List, Optional

# Conventional commit regex (shared pattern with changelog_generator / commit_splitter)
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<description>.+)$"
)

# Type → human-readable category for Changes section
_TYPE_LABEL = {
    "feat": "Features",
    "fix": "Bug fixes",
    "refactor": "Refactoring",
    "perf": "Performance",
    "docs": "Documentation",
    "test": "Tests",
    "style": "Style",
    "chore": "Chores",
    "ci": "CI/CD",
    "build": "Build",
    "sec": "Security",
}

# Branch prefix → PR intent hint
_BRANCH_INTENT = {
    "feature": "Add",
    "feat": "Add",
    "fix": "Fix",
    "bugfix": "Fix",
    "hotfix": "Hotfix",
    "refactor": "Refactor",
    "docs": "Document",
    "chore": "Maintain",
    "ci": "Update CI for",
    "release": "Release",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_branch(branch_name: str) -> Dict[str, str]:
    """Extract prefix and slug from branch name.

    Examples:
        "feature/add-jwt-auth" -> {"prefix": "feature", "slug": "add-jwt-auth"}
        "fix/null-pointer"     -> {"prefix": "fix", "slug": "null-pointer"}
        "main"                 -> {"prefix": "", "slug": "main"}
    """
    if "/" in branch_name:
        prefix, slug = branch_name.split("/", 1)
        return {"prefix": prefix, "slug": slug}
    return {"prefix": "", "slug": branch_name}


def _slug_to_words(slug: str) -> str:
    """Convert a branch slug to human-readable words.

    "add-jwt-auth" -> "add jwt auth"
    "null_pointer_fix" -> "null pointer fix"
    """
    return slug.replace("-", " ").replace("_", " ").strip()


def _parse_commit(message: str) -> Dict[str, str]:
    """Parse a conventional commit message into components.

    Returns dict with keys: type, scope, description.
    Non-conventional messages get type="" and the full message as description.
    """
    match = _CONVENTIONAL_RE.match(message.strip())
    if match:
        return {
            "type": match.group("type").lower(),
            "scope": match.group("scope") or "",
            "description": match.group("description").strip(),
        }
    return {"type": "", "scope": "", "description": message.strip()}


def _group_commits_by_type(
    commits: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, str]]]:
    """Group parsed commits by their conventional type.

    Returns dict mapping type label -> list of parsed commits.
    Non-conventional commits go under "Other".
    """
    groups: Dict[str, List[Dict[str, str]]] = {}
    for commit in commits:
        message = commit.get("message", "").strip()
        if not message:
            continue
        parsed = _parse_commit(message)
        commit_type = parsed["type"]
        label = _TYPE_LABEL.get(commit_type, "Other")
        groups.setdefault(label, []).append(parsed)
    return groups


def _group_commits_by_scope(
    commits: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Group commit descriptions by scope for the Changes section.

    Returns dict mapping scope -> list of descriptions.
    Commits without scope are grouped under their type label.
    """
    groups: Dict[str, List[str]] = {}
    for commit in commits:
        message = commit.get("message", "").strip()
        if not message:
            continue
        parsed = _parse_commit(message)
        scope = parsed["scope"]
        if not scope:
            # Use type label or "general" as fallback scope
            scope = _TYPE_LABEL.get(parsed["type"], "general")
        groups.setdefault(scope, []).append(parsed["description"])
    return groups


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def _generate_summary(
    branch_name: str,
    commits: List[Dict[str, Any]],
    diff_stats: Dict[str, Any],
) -> List[str]:
    """Generate 1-3 bullet points summarizing the PR.

    Strategy:
    1. Derive intent from branch prefix + slug.
    2. Pull key commit descriptions (feat/fix first).
    3. Add diff stats context.
    """
    lines: List[str] = []
    branch_info = _parse_branch(branch_name)
    intent = _BRANCH_INTENT.get(branch_info["prefix"], "")
    slug_words = _slug_to_words(branch_info["slug"])

    # Collect feature/fix descriptions for summary bullets
    feat_descs: List[str] = []
    fix_descs: List[str] = []
    other_descs: List[str] = []

    for commit in commits:
        message = commit.get("message", "").strip()
        if not message:
            continue
        parsed = _parse_commit(message)
        if parsed["type"] == "feat":
            feat_descs.append(parsed["description"])
        elif parsed["type"] == "fix":
            fix_descs.append(parsed["description"])
        elif parsed["type"] not in ("test", "docs", "style", "ci", "chore"):
            other_descs.append(parsed["description"])

    # Build bullets: prioritize feat, then fix, then other
    all_descs = feat_descs + fix_descs + other_descs

    if all_descs:
        # Use up to 3 unique descriptions
        seen = set()
        for desc in all_descs:
            if desc not in seen and len(lines) < 3:
                # Capitalize first letter
                bullet = desc[0].upper() + desc[1:] if len(desc) > 1 else desc.upper()
                lines.append(f"- {bullet}")
                seen.add(desc)
    elif slug_words:
        # Fallback: derive from branch name
        prefix = f"{intent} " if intent else ""
        lines.append(f"- {prefix}{slug_words}")

    # If we still have no bullets, add a generic one
    if not lines:
        lines.append("- Update project")

    # Add diff stats bullet if meaningful
    files_changed = diff_stats.get("files_changed", 0)
    insertions = diff_stats.get("insertions", 0)
    deletions = diff_stats.get("deletions", 0)
    if files_changed > 0:
        lines.append(
            f"- {files_changed} file{'s' if files_changed != 1 else ''} changed"
            f" (+{insertions}, -{deletions})"
        )

    return lines


# ---------------------------------------------------------------------------
# Changes generation
# ---------------------------------------------------------------------------

def _generate_changes(commits: List[Dict[str, Any]]) -> List[str]:
    """Generate the Changes section listing changes by scope/category."""
    lines: List[str] = []
    scope_groups = _group_commits_by_scope(commits)

    if not scope_groups:
        lines.append("- No changes recorded")
        return lines

    for scope, descriptions in sorted(scope_groups.items()):
        # Summarize descriptions for this scope
        unique_descs = []
        seen = set()
        for d in descriptions:
            if d not in seen:
                unique_descs.append(d)
                seen.add(d)

        if len(unique_descs) == 1:
            lines.append(f"- **{scope}**: {unique_descs[0]}")
        else:
            # Combine descriptions
            combined = "; ".join(unique_descs[:3])
            if len(unique_descs) > 3:
                combined += f" (+{len(unique_descs) - 3} more)"
            lines.append(f"- **{scope}**: {combined}")

    return lines


# ---------------------------------------------------------------------------
# Testing generation
# ---------------------------------------------------------------------------

def _generate_testing(commits: List[Dict[str, Any]]) -> List[str]:
    """Generate the Testing section from test-related commits."""
    lines: List[str] = []
    test_descs: List[str] = []

    for commit in commits:
        message = commit.get("message", "").strip()
        if not message:
            continue
        parsed = _parse_commit(message)
        if parsed["type"] == "test":
            test_descs.append(parsed["description"])

    if test_descs:
        seen = set()
        for desc in test_descs:
            if desc not in seen:
                bullet = desc[0].upper() + desc[1:] if len(desc) > 1 else desc.upper()
                lines.append(f"- {bullet}")
                seen.add(desc)
    else:
        lines.append("- No test changes in this PR")

    return lines


# ---------------------------------------------------------------------------
# Checklist generation
# ---------------------------------------------------------------------------

_CHECKLIST_ITEMS = [
    "- [ ] Tests pass",
    "- [ ] No breaking changes",
    "- [ ] Documentation updated",
]


def _generate_checklist() -> List[str]:
    """Return standard PR checklist items."""
    return list(_CHECKLIST_ITEMS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pr_description(
    branch_name: str,
    commits: List[Dict[str, Any]],
    diff_stats: Dict[str, Any],
) -> str:
    """Generate a structured PR description in markdown.

    Args:
        branch_name: Git branch name (e.g., "feature/add-jwt-auth").
        commits: List of dicts with ``message`` (str) and optional ``hash`` (str).
        diff_stats: Dict with optional ``files_changed`` (int),
            ``insertions`` (int), ``deletions`` (int).

    Returns:
        Formatted markdown string with sections:
        Summary, Changes, Testing, Checklist.
    """
    if not isinstance(commits, list):
        commits = []
    if not isinstance(diff_stats, dict):
        diff_stats = {}

    sections: List[str] = []

    # Summary
    sections.append("## Summary")
    sections.extend(_generate_summary(branch_name, commits, diff_stats))
    sections.append("")

    # Changes
    sections.append("## Changes")
    sections.extend(_generate_changes(commits))
    sections.append("")

    # Testing
    sections.append("## Testing")
    sections.extend(_generate_testing(commits))
    sections.append("")

    # Checklist
    sections.append("## Checklist")
    sections.extend(_generate_checklist())

    return "\n".join(sections)


def write_pr_description(
    branch_name: str,
    commits: List[Dict[str, Any]],
    diff_stats: Dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    """Generate PR description; write to *output_path* when given, else return string.

    Args:
        branch_name: Git branch name.
        commits: List of commit dicts.
        diff_stats: Diff statistics dict.
        output_path: File path to write. If None, returns string only.

    Returns:
        The generated PR description string (always returned, even when writing to file).
    """
    content = generate_pr_description(branch_name, commits, diff_stats)
    if not content:
        return ""

    if output_path is not None:
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    return content


# ---------------------------------------------------------------------------
# CLI entry point (dry-run only)
# ---------------------------------------------------------------------------

def main():
    """CLI entry point — prints PR description to stdout (dry-run)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG PR Description Generator — generates structured PR markdown"
    )
    parser.add_argument(
        "--branch", default="feature/unknown",
        help="Branch name (default: feature/unknown)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    # Minimal demo with empty data
    commits: List[Dict[str, Any]] = []
    diff_stats: Dict[str, Any] = {}

    result = write_pr_description(
        args.branch, commits, diff_stats, output_path=args.output,
    )
    if args.output is None:
        print(result)
    else:
        print(f"[OMG PR] Description written to {args.output}")


if __name__ == "__main__":
    main()
