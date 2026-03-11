"""Protected context registry for PreCompact hook.

Reads .claude-context-protect entries (file paths, regex patterns, literal strings)
and collects protected context items to re-inject via additionalContext during compaction.

Default protections (when no .claude-context-protect exists):
- CLAUDE.md content
- Active task definitions (## Task:, - [ ])
- Recent error messages (Error:, Exception:, FAILED)

Pure stdlib — no external dependencies.
"""
import os
import re


PROTECT_FILE_NAME = ".claude-context-protect"

# Default protection patterns (used when no protect file exists)
_DEFAULT_TASK_PATTERNS = [
    re.compile(r"^## Task:"),
    re.compile(r"^- \[ \]"),
]
_DEFAULT_ERROR_KEYWORDS = ("Error:", "Exception:", "FAILED")


def load_protect_entries(project_dir):
    """Read .claude-context-protect file, return list of entries or None if missing.

    Returns:
        list[str] | None: List of non-empty, non-comment lines. None if file missing.
    """
    protect_path = os.path.join(project_dir, PROTECT_FILE_NAME)
    if not os.path.isfile(protect_path):
        return None

    try:
        with open(protect_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return None

    entries = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.append(stripped)
    return entries


def _read_file_content(file_path):
    """Read file content. Returns stripped string or None on failure."""
    try:
        if not os.path.isfile(file_path):
            return None
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        return content if content else None
    except Exception:
        return None


def _match_entry_against_lines(entry, context_lines):
    """Match entry against context lines. Tries regex first, falls back to literal.

    Returns:
        list[str]: Matching lines.
    """
    try:
        pattern = re.compile(entry)
        return [line for line in context_lines if pattern.search(line)]
    except re.error:
        # Invalid regex — fall back to literal substring match
        return [line for line in context_lines if entry in line]


def _process_entry(entry, project_dir, context_lines):
    """Process a single protect entry. Returns list of protected strings.

    Resolution order:
    1. If entry resolves to an existing file → include file content
    2. Otherwise, try regex match against context lines
    3. If regex fails (re.error), fall back to literal substring match
    """
    # 1. Try as file path
    file_path = os.path.join(project_dir, entry)
    content = _read_file_content(file_path)
    if content is not None:
        return [content]

    # 2. Try as regex/literal against context lines
    return _match_entry_against_lines(entry, context_lines)


def _get_default_protections(project_dir, context_lines):
    """Apply default protections when no .claude-context-protect exists.

    Default protected items:
    - CLAUDE.md content (if file exists)
    - Active task definitions (## Task:, - [ ])
    - Recent error messages (Error:, Exception:, FAILED)
    """
    parts = []

    # 1. CLAUDE.md content
    claude_md_path = os.path.join(project_dir, "CLAUDE.md")
    claude_content = _read_file_content(claude_md_path)
    if claude_content:
        parts.append(claude_content)

    # 2. Active task definitions
    for line in context_lines:
        for pat in _DEFAULT_TASK_PATTERNS:
            if pat.search(line):
                parts.append(line)
                break

    # 3. Recent error messages
    for line in context_lines:
        if any(kw in line for kw in _DEFAULT_ERROR_KEYWORDS):
            parts.append(line)

    return parts


def collect_protected_context(project_dir, context_text=""):
    """Collect all protected context items and return as a single string.

    Args:
        project_dir: Project root directory.
        context_text: Current context text to scan for regex/literal matches.

    Returns:
        str: Protected context items joined by newlines. Empty string if nothing.
    """
    context_lines = [l for l in context_text.split("\n") if l.strip()] if context_text else []
    protected_parts = []

    entries = load_protect_entries(project_dir)

    if entries is None:
        # No protect file — use defaults
        protected_parts = _get_default_protections(project_dir, context_lines)
    else:
        # Process each entry from protect file
        for entry in entries:
            matched = _process_entry(entry, project_dir, context_lines)
            protected_parts.extend(matched)

    return "\n".join(protected_parts) if protected_parts else ""
