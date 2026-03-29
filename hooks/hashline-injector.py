#!/usr/bin/env python3
"""Hashline Injector — injects content-hash anchors into file content on read.

Each line gets a tag: `{line_number}#{2-char-id}|{original line}`
where the 2-char ID is derived from SHA-256 of the line content mapped to
the charset ZPMQVRWSNKTXJBYH (16 chars, 4-bit nibbles of first hash byte).

Uses a sidecar cache at `.omg/state/hashline_cache.json` to avoid
regenerating hashes for unchanged files. Never modifies original files.

Feature flag: OMG_HASHLINE_ENABLED (default: False)
"""
import hashlib
import json
import os
import re
import sys
import time

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from hooks._common import (
    setup_crash_handler,
    json_input,
    get_feature_flag,
    get_project_dir,
    atomic_json_write,
)

setup_crash_handler("hashline-injector")

# --- Constants ---

# 16-char charset for 4-bit nibble mapping
HASH_CHARSET = "ZPMQVRWSNKTXJBYH"

# Regex to strip hashline prefix: digits + # + 2 uppercase letters + |
_HASHLINE_RE = re.compile(r"^\d+#[A-Z]{2}\|")

# Sidecar cache path (relative to project dir)
_CACHE_REL_PATH = os.path.join(".omg", "state", "hashline_cache.json")


# --- Core Functions ---


def _line_hash_id(line: str) -> str:
    """Generate 2-char hash ID from line content.

    Takes first byte of SHA-256 digest, splits into two 4-bit nibbles,
    maps each nibble to HASH_CHARSET.
    """
    digest = hashlib.sha256(line.encode("utf-8", errors="replace")).digest()
    first_byte = digest[0]
    high_nibble = (first_byte >> 4) & 0x0F
    low_nibble = first_byte & 0x0F
    return HASH_CHARSET[high_nibble] + HASH_CHARSET[low_nibble]


def inject_hashlines(content: str, file_path: str | None = None) -> str:
    """Add hash anchors to each line of content.

    Format: `{line_num}#{hash_id}|{original_line}` (1-indexed)

    Args:
        content: File content string
        file_path: Optional file path for caching. If provided and the file
                   exists, hashes are cached to `.omg/state/hashline_cache.json`.

    Returns:
        Content with hash anchors prepended to each line.
        Returns content unchanged if OMG_HASHLINE_ENABLED is False.
    """
    if not _is_enabled():
        return content

    # Check cache first
    if file_path:
        cached = _get_cached_hashes(file_path)
        if cached is not None:
            return _apply_cached_hashes(content, cached)

    lines = content.split("\n")
    result = []
    line_hashes = {}

    for i, line in enumerate(lines, start=1):
        hash_id = _line_hash_id(line)
        line_hashes[str(i)] = hash_id
        result.append(f"{i}#{hash_id}|{line}")

    # Cache if file_path provided
    if file_path:
        _cache_hashes(file_path, line_hashes)

    return "\n".join(result)


def strip_hashlines(content: str) -> str:
    """Remove hash anchors from content, restoring original text.

    Strips `^\\d+#[A-Z]{2}\\|` prefix from each line.

    Args:
        content: Content with hash anchors

    Returns:
        Original content without hash anchors.
    """
    lines = content.split("\n")
    result = []
    for line in lines:
        result.append(_HASHLINE_RE.sub("", line))
    return "\n".join(result)


def _apply_cached_hashes(content: str, line_hashes: dict[str, str]) -> str:
    """Apply cached hash IDs to content lines."""
    lines = content.split("\n")
    result = []
    for i, line in enumerate(lines, start=1):
        hash_id = line_hashes.get(str(i))
        if hash_id is None:
            # Line count changed — cache is stale, regenerate
            hash_id = _line_hash_id(line)
        result.append(f"{i}#{hash_id}|{line}")
    return "\n".join(result)


# --- Sidecar Cache ---


def _get_cache_path() -> str:
    """Get absolute path to hashline cache file."""
    return os.path.join(get_project_dir(), _CACHE_REL_PATH)


def _load_cache() -> dict[str, dict[str, object]]:
    """Load the entire hashline cache from disk. Returns empty dict on failure."""
    cache_path = _get_cache_path()
    try:
        if not os.path.exists(cache_path):
            return {}
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_cached_hashes(file_path: str) -> dict[str, str] | None:
    """Get cached line hashes for a file, if still valid.

    Args:
        file_path: Path to the source file

    Returns:
        dict mapping line number (str) -> hash_id, or None if not cached
        or if the file's mtime has changed (cache invalidation).
    """
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return None

        cache = _load_cache()
        entry = cache.get(abs_path)
        if entry is None:
            return None

        # Check mtime for invalidation
        current_mtime = os.path.getmtime(abs_path)
        cached_mtime_raw = entry.get("mtime", 0)
        cached_mtime = float(cached_mtime_raw) if isinstance(cached_mtime_raw, (int, float)) else 0.0
        if abs(current_mtime - cached_mtime) > 0.001:
            return None

        line_hashes = entry.get("line_hashes")
        if isinstance(line_hashes, dict):
            return {str(k): str(v) for k, v in line_hashes.items()}
        return None
    except Exception:
        return None


def _cache_hashes(file_path: str, line_hashes: dict[str, str]) -> None:
    """Save line hashes to sidecar cache with mtime for invalidation.

    Args:
        file_path: Path to the source file
        line_hashes: dict mapping line number (str) -> hash_id
    """
    try:
        abs_path = os.path.abspath(file_path)
        cache = _load_cache()

        mtime = 0.0
        if os.path.exists(abs_path):
            mtime = os.path.getmtime(abs_path)

        cache[abs_path] = {
            "mtime": mtime,
            "line_hashes": line_hashes,
        }

        atomic_json_write(_get_cache_path(), cache)
    except Exception:
        try:
            print(f"[omg:warn] [hashline-injector] failed to cache line hashes: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass


# --- Feature Flag ---


def _is_enabled() -> bool:
    """Check if hashline injection is enabled.

    Resolution order: OMG_HASHLINE_ENABLED env var → settings.json → False
    """
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_HASHLINE_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    # Slow path: check settings.json via get_feature_flag
    return get_feature_flag("HASHLINE", default=False)


# --- Hook Entry Point ---


def main():
    """Hook stdin/stdout entry point for Claude Code PreToolUse hooks.

    Reads JSON from stdin with tool_input containing file content.
    If hashline injection is enabled and tool is a file read, injects
    hash anchors into the content.
    Writes modified tool input back to stdout.
    Always exits 0 — never raises.
    """
    if not _is_enabled():
        sys.exit(0)

    data = json_input()
    if not isinstance(data, dict):
        sys.exit(0)

    # Only inject for file-read tools
    tool_name = data.get("tool_name", "")
    if tool_name not in ("Read", "mcp__filesystem__read_file",
                          "mcp__filesystem__read_text_file"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        sys.exit(0)

    content = tool_input.get("content", "")
    file_path = tool_input.get("file_path", tool_input.get("filePath", ""))

    if not content:
        sys.exit(0)

    try:
        injected = inject_hashlines(content, file_path or None)
        tool_input["content"] = injected
        data["tool_input"] = tool_input
        json.dump(data, sys.stdout)
    except Exception:
        try:
            print(f"[omg:warn] [hashline-injector] failed to inject hashlines: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
