#!/usr/bin/env python3
"""
AI Commit Splitter for OMG

Analyzes git changes and groups them into logical atomic commits
with hunk-level staging support. Read-only analysis — never runs git commit.

Feature flag: OMG_AI_COMMIT_ENABLED (default: False)
"""

import json
import os
import re
import shlex
import subprocess
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
    if _get_feature_flag is None:
        return False
    return bool(_get_feature_flag("GIT_WORKFLOW", default=False))


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

_QUALITY_STEPS = ["format", "lint", "typecheck", "test"]

_ALLOWED_PREFIXES = [
    ("npm", "test"),
    ("yarn", "test"),
    ("pnpm", "test"),
    ("bun", "test"),
    ("npx", "--no-install", "prettier"),
    ("npx", "--no-install", "eslint"),
    ("npx", "--no-install", "tsc"),
    ("npx", "--no-install", "jest"),
    ("npx", "--no-install", "vitest"),
    ("npx", "--no-install", "biome"),
    ("jest",),
    ("vitest",),
    ("eslint",),
    ("prettier",),
    ("tsc",),
    ("biome",),
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("ruff",),
    ("mypy",),
    ("flake8",),
    ("black",),
    ("isort",),
    ("bandit",),
    ("pylint",),
    ("go", "test"),
    ("go", "vet"),
    ("go", "build"),
    ("golangci-lint",),
    ("cargo", "test"),
    ("cargo", "check"),
    ("cargo", "build"),
    ("cargo", "clippy"),
    ("cargo", "fmt"),
    ("shellcheck",),
]

_BLOCKED_PATTERNS = [
    "&&", "||", "|", ";", "`", "$(", "${", ">", "<", "\n",
    "rm ", "curl ", "wget ", "eval ", "exec ", "sudo ",
]

_CONVENTIONAL_COMMIT_RE = re.compile(r"^(feat|fix|chore|refactor|docs|test|ci|style|perf|build)(\([^)]+\))?: .+")


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


def _derive_scope_from_prefix(files: List[str], prefix_dirs: tuple[str, ...]) -> str:
    """Derive scope from subdirectory after a type-matched prefix."""
    from collections import Counter

    sub_dirs: List[str] = []
    for f in files:
        norm = f.replace("\\", "/")
        matched_prefix = ""
        for prefix in prefix_dirs:
            if norm.startswith(prefix):
                matched_prefix = prefix
                break

        if matched_prefix:
            remainder = norm[len(matched_prefix):]
            parts = remainder.split("/")
            if len(parts) > 1:
                sub_dirs.append(parts[0])
            else:
                sub_dirs.append(matched_prefix.rstrip("/"))
        else:
            parts = norm.split("/")
            if len(parts) > 1:
                sub_dirs.append(parts[0])
            else:
                name, _ = os.path.splitext(parts[0])
                sub_dirs.append(name)

    if not sub_dirs:
        return "general"

    counts = Counter(sub_dirs)
    return counts.most_common(1)[0][0]


# --- Commit type detection by path ---

# Prefix directories → commit type
_PATH_PREFIX_TYPE = {
    "src/": "feat",
    "lib/": "feat",
    "app/": "feat",
    "hooks/": "feat",
    "tests/": "test",
    "test/": "test",
    "spec/": "test",
    "docs/": "docs",
}

# Fix-related path keywords
_FIX_KEYWORDS = ("fix", "bug", "patch", "hotfix")

# Config file extensions (checked when no prefix matches)
_CONFIG_EXTENSIONS = (".json", ".yaml", ".yml", ".toml", ".cfg")

# Config file name patterns (basename startswith or exact match)
_CONFIG_BASENAMES = ("setup.", "makefile")


def _detect_commit_type(file_path: str) -> str:
    """Detect commit type from file path. Priority: fix keywords → prefix → docs → config → chore."""
    norm = file_path.replace("\\", "/").lower()

    for keyword in _FIX_KEYWORDS:
        if ("/" + keyword) in norm or norm.startswith(keyword):
            return "fix"

    for prefix, commit_type in _PATH_PREFIX_TYPE.items():
        if norm.startswith(prefix):
            return commit_type

    basename = os.path.basename(norm)
    if basename.startswith("readme") or basename == "changelog.md":
        return "docs"
    _, ext = os.path.splitext(norm)
    if ext == ".md":
        return "docs"

    if ext in _CONFIG_EXTENSIONS:
        return "chore"
    for config_name in _CONFIG_BASENAMES:
        if basename.startswith(config_name) or basename == config_name.rstrip("."):
            return "chore"

    return "chore"


def _detect_type_majority(files: List[str]) -> str:
    """Detect commit type by majority vote across files."""
    if not files:
        return "chore"

    from collections import Counter
    types = [_detect_commit_type(f) for f in files]
    counts = Counter(types)
    return counts.most_common(1)[0][0]


def _prefix_dirs_for_type(commit_type: str) -> tuple:
    result = [p for p, t in _PATH_PREFIX_TYPE.items() if t == commit_type]
    return tuple(result) if result else ("",)


def generate_commit_message(diff_stats: Dict[str, Any]) -> str:
    """Generate conventional commit message: type(scope): description.

    Args:
        diff_stats: Dict with ``files`` (list[str]), optional ``description``
            (str), and optional ``breaking_change`` (str).
    """
    files: List[str] = diff_stats.get("files", [])
    description: str = diff_stats.get("description", "")
    breaking_change: str = diff_stats.get("breaking_change", "")

    commit_type = _detect_type_majority(files)

    prefix_dirs = _prefix_dirs_for_type(commit_type)
    scope = _derive_scope_from_prefix(files, prefix_dirs) if files else "general"

    if not description:
        if files:
            category = _classify_file(files[0])
            description = _derive_description(category, files)
        else:
            description = "update project"

    prefix = f"{commit_type}({scope}): "
    max_desc_len = 72 - len(prefix)
    if max_desc_len < 1:
        max_desc_len = 1
    if len(description) > max_desc_len:
        description = description[:max_desc_len - 3].rstrip() + "..."

    subject = f"{prefix}{description}"

    if breaking_change:
        return f"{subject}\n\nBREAKING CHANGE: {breaking_change}"

    return subject


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


def _is_safe_command(cmd: str) -> tuple[bool, str, list[str]]:
    cmd = cmd.strip()
    cmd_lower = cmd.lower()

    for pattern in _BLOCKED_PATTERNS:
        target = cmd_lower if any(ch.isalpha() for ch in pattern) else cmd
        if pattern in target:
            return False, f"blocked pattern '{pattern}'", []

    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return False, f"invalid command syntax: {exc}", []

    if not argv:
        return False, "empty command", []

    for prefix in _ALLOWED_PREFIXES:
        if len(argv) < len(prefix):
            continue
        if tuple(argv[: len(prefix)]) == prefix:
            return True, "", argv

    return False, "not in allowed commands list", []


def _load_quality_gate_config(project_dir: str) -> Optional[dict[str, str]]:
    primary = os.path.join(project_dir, ".omg", "state", "quality-gate.json")
    legacy = os.path.join(project_dir, ".omc", "quality-gate.json")
    path = primary if os.path.exists(primary) else legacy

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)

    if not isinstance(loaded, dict):
        raise ValueError("quality-gate.json must be a JSON object")

    config: dict[str, str] = {}
    for key, value in loaded.items():
        if isinstance(key, str) and isinstance(value, str):
            config[key] = value
    return config


def _run_quality_gate(project_dir: str) -> Dict[str, Any]:
    try:
        config = _load_quality_gate_config(project_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "step": "config", "reason": str(exc), "results": []}

    if not config:
        return {"ok": True, "results": []}

    results: list[str] = []
    for step in _QUALITY_STEPS:
        cmd = config.get(step)
        if cmd is None or not cmd.strip():
            continue

        safe, reason, argv = _is_safe_command(cmd)
        if not safe:
            return {
                "ok": False,
                "step": step,
                "reason": f"{cmd} ({reason})",
                "results": results,
            }

        try:
            run_result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=project_dir,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "step": step,
                "reason": f"TIMEOUT {step}: {cmd}",
                "results": results,
            }
        except FileNotFoundError:
            results.append(f"SKIP {step}: command not found ({cmd})")
            continue

        if run_result.returncode != 0:
            snippet = (run_result.stderr or run_result.stdout).strip()[:300]
            return {
                "ok": False,
                "step": step,
                "reason": f"FAIL {step}: {cmd} (exit {run_result.returncode}) {snippet}",
                "results": results,
            }
        results.append(f"PASS {step}: {cmd} (exit 0)")

    return {"ok": True, "results": results}


def execute_commit_plan(plan: List[Dict[str, Any]], project_dir: str, dry_run: bool = False) -> Dict[str, Any]:
    if not isinstance(plan, list):
        raise ValueError("plan must be a list")

    for idx, group in enumerate(plan):
        if not isinstance(group, dict):
            raise ValueError(f"plan[{idx}] must be a dict")
        files = group.get("files")
        message = group.get("message")
        if not isinstance(files, list) or not files or not all(isinstance(p, str) and p for p in files):
            raise ValueError(f"plan[{idx}] must include non-empty files list")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"plan[{idx}] must include non-empty message")
        if _CONVENTIONAL_COMMIT_RE.match(message.strip()) is None:
            raise ValueError(f"plan[{idx}] message must be conventional commit format")

    result: Dict[str, Any] = {
        "succeeded": [],
        "failed": None,
        "aborted": [],
    }

    if dry_run:
        for group in plan:
            files = group["files"]
            message = group["message"].strip()
            print(f"[DRY-RUN] git add {' '.join(files)}")
            print(f"[DRY-RUN] git commit -m {message}")
        return result

    for idx, group in enumerate(plan):
        files = group["files"]
        message = group["message"].strip()

        gate = _run_quality_gate(project_dir)
        if not gate.get("ok", False):
            result["failed"] = {
                "message": message,
                "files": files,
                "stage": "quality_gate",
                "reason": gate.get("reason", "quality gate failed"),
            }
            result["aborted"] = [remaining["message"] for remaining in plan[idx + 1:]]
            return result

        add_cmd = ["git", "-C", project_dir, "add", *files]
        add_result = subprocess.run(
            add_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_dir,
        )
        if add_result.returncode != 0:
            result["failed"] = {
                "message": message,
                "files": files,
                "stage": "git_add",
                "reason": (add_result.stderr or add_result.stdout).strip(),
            }
            result["aborted"] = [remaining["message"] for remaining in plan[idx + 1:]]
            return result

        commit_cmd = ["git", "-C", project_dir, "commit", "-m", message]
        commit_result = subprocess.run(
            commit_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_dir,
        )
        if commit_result.returncode != 0:
            result["failed"] = {
                "message": message,
                "files": files,
                "stage": "git_commit",
                "reason": (commit_result.stderr or commit_result.stdout).strip(),
            }
            result["aborted"] = [remaining["message"] for remaining in plan[idx + 1:]]
            return result

        result["succeeded"].append(message)

    return result


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
    if _git_inspector is None:
        return []
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
