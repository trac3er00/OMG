#!/usr/bin/env python3
"""Hashline Validator — validates edit targets against stored hash anchors.

Validates that ``line_ref`` (e.g. ``"11#VK"``) matches the cached hash for
that line before allowing an edit.  Rejects mismatched edits with a clear
error dict.  Updates cache after successful edits.

Feature flag: OAL_HASHLINE_ENABLED (default: False)
"""
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import (
    setup_crash_handler,
    json_input,
    get_feature_flag,
)

setup_crash_handler("hashline-validator")

# --- Constants ---

# Valid line_ref: digits + # + exactly 2 chars from HASH_CHARSET
_LINE_REF_RE = re.compile(r"^\d+#[ZPMQVRWSNKTXJBYH]{2}$")


# --- Feature Flag ---


def _is_enabled() -> bool:
    """Check if hashline validation is enabled.

    Resolution order: OAL_HASHLINE_ENABLED env var → settings.json → False
    """
    env_val = os.environ.get("OAL_HASHLINE_ENABLED", "").lower()
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


def validate_line_ref_format(line_ref: str) -> bool:
    """Return True if *line_ref* matches ``'{line_num}#{2-char hash_id}'``.

    Hash ID characters must belong to the charset ``ZPMQVRWSNKTXJBYH``.

    Args:
        line_ref: Line reference string (e.g. ``"11#VK"``)

    Returns:
        True if format is valid, False otherwise.
    """
    if not isinstance(line_ref, str):
        return False
    return bool(_LINE_REF_RE.match(line_ref))


def validate_edit(file_path: str, line_ref: str, expected_line: str) -> dict:
    """Validate a hash anchor before allowing an edit.

    Args:
        file_path: Path to the file being edited.
        line_ref: Line reference ``"{line_num}#{hash_id}"`` (e.g. ``"11#VK"``).
        expected_line: The expected content of the line (context, not used
                       for hash matching itself).

    Returns:
        dict with validation result — always contains ``"valid"`` key:

        * Feature disabled → ``{"valid": True, "skipped": True}``
        * No cache available → ``{"valid": True, "uncached": True}``
        * Hash match → ``{"valid": True, "line": <int>}``
        * Hash mismatch → ``{"valid": False, "error": "HASH_MISMATCH",
          "line": <int>, "expected": <str>, "actual": <str>}``
        * Bad format → ``{"valid": False, "error": "INVALID_LINE_REF",
          "line_ref": <str>}``
    """
    # Skip when disabled
    if not _is_enabled():
        return {"valid": True, "skipped": True}

    # Validate format
    if not validate_line_ref_format(line_ref):
        return {"valid": False, "error": "INVALID_LINE_REF", "line_ref": line_ref}

    # Parse line_ref
    parts = line_ref.split("#")
    line_num = int(parts[0])
    hash_id = parts[1]

    # Load cache via injector
    try:
        injector = _get_injector()
        cached_hashes = injector._get_cached_hashes(file_path)
    except Exception:
        # Injector unavailable — cannot validate
        return {"valid": True, "uncached": True}

    if cached_hashes is None:
        return {"valid": True, "uncached": True}

    # Look up the line in the cache
    stored_hash = cached_hashes.get(str(line_num))
    if stored_hash is None:
        # Line number not in cache (file may have grown since last cache)
        return {"valid": True, "uncached": True}

    # Compare
    if stored_hash != hash_id:
        return {
            "valid": False,
            "error": "HASH_MISMATCH",
            "line": line_num,
            "expected": hash_id,
            "actual": stored_hash,
        }

    return {"valid": True, "line": line_num}


def update_hashes_after_edit(file_path: str, new_content: str) -> bool:
    """Refresh the hash cache after a successful edit.

    Re-generates line hashes for *new_content* and updates the sidecar
    cache (``hashline_cache.json``) for *file_path*.

    Args:
        file_path: Path to the edited file.
        new_content: The file content after the edit.

    Returns:
        True on success (or when disabled), False on error.
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
        lines = new_content.split("\n")
        line_hashes = {}
        for i, line in enumerate(lines, start=1):
            line_hashes[str(i)] = _line_hash_id(line)

        _cache_hashes(file_path, line_hashes)
        return True
    except Exception:
        return False


# --- Hook Entry Point ---


def main():
    """Hook stdin/stdout entry point.

    Reads JSON from stdin::

        {"file_path": "...", "line_ref": "11#VK", "expected_line": "..."}

    Calls :func:`validate_edit` and writes the result dict to stdout.
    Always exits 0 — never raises.
    """
    if not _is_enabled():
        json.dump({"valid": True, "skipped": True}, sys.stdout)
        sys.exit(0)

    data = json_input()
    if not isinstance(data, dict):
        json.dump({"valid": False, "error": "INVALID_INPUT"}, sys.stdout)
        sys.exit(0)

    file_path = data.get("file_path", "")
    line_ref = data.get("line_ref", "")
    expected_line = data.get("expected_line", "")

    try:
        result = validate_edit(file_path, line_ref, expected_line)
        json.dump(result, sys.stdout)
    except Exception:
        json.dump({"valid": False, "error": "INTERNAL_ERROR"}, sys.stdout)

    sys.exit(0)


if __name__ == "__main__":
    main()
