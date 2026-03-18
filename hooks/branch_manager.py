#!/usr/bin/env python3
"""SessionStart Hook — Smart Branch Manager.

Auto-creates a feature branch when on main/master/develop.
Extracts task description from OMG state files for branch naming.

Feature-gated: OMG_GIT_WORKFLOW_ENABLED (uses get_feature_flag('GIT_WORKFLOW'))
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, get_feature_flag

setup_crash_handler("branch-manager", fail_closed=False)

# Default branches that trigger feature branch creation
DEFAULT_BRANCHES = frozenset({"main", "master", "develop"})

# Max length for the descriptive part of branch name
MAX_BRANCH_NAME_LEN = 50


def _get_project_dir() -> str:
    """Get project directory from env or cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _has_git(project_dir: str) -> bool:
    """Check if project_dir is inside a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _current_branch(project_dir: str) -> str | None:
    """Get current branch name. Returns None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _sanitize_branch_name(description: str) -> str:
    """Sanitize a description into a valid git branch name segment.

    Rules:
    - Lowercase
    - Replace spaces/underscores with hyphens
    - Strip special characters (keep alphanumeric and hyphens)
    - Collapse consecutive hyphens
    - Strip leading/trailing hyphens
    - Max MAX_BRANCH_NAME_LEN chars
    """
    name = description.lower().strip()
    # Replace spaces and underscores with hyphens
    name = re.sub(r"[\s_]+", "-", name)
    # Remove everything except alphanumeric and hyphens
    name = re.sub(r"[^a-z0-9-]", "", name)
    # Collapse consecutive hyphens
    name = re.sub(r"-{2,}", "-", name)
    # Strip leading/trailing hyphens
    name = name.strip("-")
    # Truncate to max length, but don't cut mid-word if possible
    if len(name) > MAX_BRANCH_NAME_LEN:
        truncated = name[:MAX_BRANCH_NAME_LEN]
        # Try to cut at last hyphen to avoid mid-word truncation
        last_hyphen = truncated.rfind("-")
        if last_hyphen > 20:
            truncated = truncated[:last_hyphen]
        name = truncated.rstrip("-")
    return name


def _extract_task_description(project_dir: str) -> str | None:
    """Extract task description from OMG state files.

    Priority order:
    (a) .omg/state/_plan.md title (first # heading)
    (b) .omg/state/_checklist.md first item
    (c) .omg/state/working-memory.md last entry
    (d) fallback: None (caller uses session-{timestamp})
    """
    state_dir = os.path.join(project_dir, ".omg", "state")

    # (a) Plan title
    plan_path = os.path.join(state_dir, "_plan.md")
    if os.path.isfile(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("# "):
                        title = line[2:].strip()
                        if title:
                            return title
        except Exception:
            pass

    # (b) Checklist first item
    checklist_path = os.path.join(state_dir, "_checklist.md")
    if os.path.isfile(checklist_path):
        try:
            with open(checklist_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    # Match markdown checkbox items: - [ ] or - [x]
                    m = re.match(r"^-\s*\[.\]\s*(.+)$", line)
                    if m:
                        item = m.group(1).strip()
                        if item:
                            return item
        except Exception:
            pass

    # (c) Working memory last entry
    wm_path = os.path.join(state_dir, "working-memory.md")
    if os.path.isfile(wm_path):
        try:
            with open(wm_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Split by ## headings, take last entry's content
            sections = re.split(r"\n## ", content)
            if len(sections) > 1:
                # Last section: first line is heading, rest is content
                last_lines = sections[-1].split("\n")
                # Find first non-empty content line after heading
                for line in last_lines[1:]:
                    line = line.strip()
                    if line:
                        return line
                # Fallback to heading if no content
                heading = last_lines[0].strip()
                if heading:
                    return heading
            elif sections:
                # Single section — try first non-empty non-heading line
                for line in sections[0].split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line
        except Exception:
            pass

    # (d) No state files found
    return None


def _is_merge_writer_locked(project_dir: str) -> bool:
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from runtime.merge_writer import MergeWriter  # pyright: ignore[reportMissingImports]
        return MergeWriter(project_dir).is_locked()
    except Exception:
        return False


def _create_branch(project_dir: str, branch_name: str) -> bool:
    """Create and checkout a new branch. Returns True on success."""
    if _is_merge_writer_locked(project_dir):
        print(
            f"[OMG branch-manager] Branch creation blocked: merge-writer lock is held",
            file=sys.stderr,
        )
        return False
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "checkout", "-b", branch_name],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> None:
    """Main hook entry point."""
    data = json_input()

    # Feature gate: exit silently if disabled
    if not get_feature_flag("GIT_WORKFLOW", default=False):
        sys.exit(0)

    project_dir = _get_project_dir()

    # No-op if not a git repo
    if not _has_git(project_dir):
        sys.exit(0)

    # Get current branch
    branch = _current_branch(project_dir)
    if branch is None:
        sys.exit(0)

    # No-op if already on a non-default branch (feature branch, etc.)
    if branch not in DEFAULT_BRANCHES:
        sys.exit(0)

    # Extract task description and build branch name
    description = _extract_task_description(project_dir)
    if description:
        sanitized = _sanitize_branch_name(description)
    else:
        sanitized = ""

    if not sanitized:
        # Fallback: session-{timestamp}
        sanitized = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    target_branch = f"feature/{sanitized}"

    # Dry-run mode: output what would happen without executing
    dry_run = os.environ.get("OMG_GIT_WORKFLOW_DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print(
            f"[OMG branch-manager] DRY-RUN: Would create branch '{target_branch}' from '{branch}'",
            file=sys.stderr,
        )
        sys.exit(0)

    # Create the feature branch
    success = _create_branch(project_dir, target_branch)
    if success:
        print(
            f"[OMG branch-manager] Created branch '{target_branch}' from '{branch}'",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
