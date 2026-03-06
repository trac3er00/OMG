#!/usr/bin/env python3
"""Hashline Formatter Bridge — reconciles sidecar hash cache after formatters run.

When a post-write formatter (e.g. prettier, ruff format) modifies a file,
the cached line hashes become stale.  This bridge detects the change and
refreshes the sidecar cache so subsequent reads/edits use correct anchors.

Feature flag: OMG_HASHLINE_ENABLED (default: False)
"""
import json
import os
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import (
    setup_crash_handler,
    json_input,
    get_feature_flag,
)

setup_crash_handler("hashline-formatter-bridge")


# --- Feature Flag ---


def _is_enabled() -> bool:
    """Check if hashline features are enabled.

    Resolution order: OMG_HASHLINE_ENABLED env var -> settings.json -> False
    """
    env_val = os.environ.get("OMG_HASHLINE_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    return get_feature_flag("HASHLINE", default=False)


# --- Lazy Imports from hashline-injector ---

_injector = None


def _get_injector():
    """Lazy-load hashline-injector module."""
    global _injector
    if _injector is None:
        import importlib
        _injector = importlib.import_module("hashline-injector")
    return _injector


# --- Core Functions ---


def detect_formatter_change(file_path: str, original_content: str, formatted_content: str) -> bool:
    """Return True if the formatter changed the content.

    Compares stripped versions of each line to ignore trivial
    trailing-whitespace-only differences while still detecting
    real structural changes.

    Args:
        file_path: Path to the file (for context, not read).
        original_content: Content before formatting.
        formatted_content: Content after formatting.

    Returns:
        True if formatted_content differs from original_content.
    """
    if original_content == formatted_content:
        return False

    # Compare stripped lines to ignore trivial whitespace diffs
    orig_lines = [l.rstrip() for l in original_content.split("\n")]
    fmt_lines = [l.rstrip() for l in formatted_content.split("\n")]
    return orig_lines != fmt_lines


def refresh_cache_after_format(file_path: str, formatted_content: str) -> bool:
    """Recompute and save line hashes for newly formatted content.

    Args:
        file_path: Path to the formatted file.
        formatted_content: The file content after formatting.

    Returns:
        True on success (or when feature is disabled), False on error.
    """
    if not _is_enabled():
        return True

    try:
        injector = _get_injector()
        _line_hash_id = injector._line_hash_id
        _cache_hashes = injector._cache_hashes
    except Exception:
        return False

    try:
        lines = formatted_content.split("\n")
        line_hashes = {}
        for i, line in enumerate(lines, start=1):
            line_hashes[str(i)] = _line_hash_id(line)

        _cache_hashes(file_path, line_hashes)
        return True
    except Exception:
        return False


def reconcile_post_format(file_path: str) -> dict:
    """Reconcile hash cache with the current file on disk.

    Reads the file, checks whether the cached mtime is stale
    (indicating a formatter ran after the last cache write),
    and refreshes the cache if needed.

    Args:
        file_path: Path to the file to reconcile.

    Returns:
        dict with reconciliation result:
        - ``{"skipped": True}`` when feature is disabled
        - ``{"refreshed": True/False, "lines_updated": int, "file": str}``
    """
    if not _is_enabled():
        return {"skipped": True}

    try:
        injector = _get_injector()
        _get_cached_hashes = injector._get_cached_hashes
        _line_hash_id = injector._line_hash_id
        _cache_hashes = injector._cache_hashes
    except Exception:
        return {"refreshed": False, "lines_updated": 0, "file": file_path}

    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return {"refreshed": False, "lines_updated": 0, "file": file_path}

        # Read current content from disk
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Check if cache exists — if _get_cached_hashes returns None,
        # cache is either missing or mtime doesn't match (formatter ran).
        cached = _get_cached_hashes(file_path)
        if cached is not None:
            # Cache is still valid (mtime matches) — no refresh needed
            return {"refreshed": False, "lines_updated": 0, "file": file_path}

        # Cache is stale or missing — refresh
        lines = content.split("\n")
        line_hashes = {}
        for i, line in enumerate(lines, start=1):
            line_hashes[str(i)] = _line_hash_id(line)

        _cache_hashes(file_path, line_hashes)
        return {"refreshed": True, "lines_updated": len(lines), "file": file_path}
    except Exception:
        return {"refreshed": False, "lines_updated": 0, "file": file_path}


# --- Write-tool names that trigger reconciliation ---

_WRITE_TOOLS = frozenset({
    "Write", "Edit", "MultiEdit",
    "mcp__filesystem__write_file",
    "mcp__filesystem__edit_file",
})


# --- Hook Entry Point ---


def main():
    """PostToolUse hook stdin/stdout entry point.

    Reads JSON from stdin::

        {"tool_name": "Write", "tool_input": {"file_path": "..."}}

    If tool_name is a write tool and OMG_HASHLINE_ENABLED is set,
    runs ``reconcile_post_format`` to refresh the hash cache after
    any post-write formatter may have modified the file.

    Always exits 0 — never raises.
    """
    if not _is_enabled():
        sys.exit(0)

    data = json_input()
    if not isinstance(data, dict):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in _WRITE_TOOLS:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        sys.exit(0)

    file_path = tool_input.get("file_path", tool_input.get("filePath", ""))
    if not file_path:
        sys.exit(0)

    try:
        result = reconcile_post_format(file_path)
        json.dump(result, sys.stdout)
    except Exception:
        pass  # Graceful degradation — never crash

    sys.exit(0)


if __name__ == "__main__":
    main()
