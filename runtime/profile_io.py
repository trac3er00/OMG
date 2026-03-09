"""Canonical profile I/O — single owner of profile.yaml read/write/version.

All profile consumers should use this module to load and persist profile data.
``profile_version`` is derived from a canonical key-sorted JSON hash of the
parsed dict, never from raw file text.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import yaml


def load_profile(path: str) -> dict[str, Any]:
    """Load a profile from *path*, returning a dict.

    Handles both YAML and JSON-shaped content transparently (backward compat).
    Returns ``{}`` when the file is missing or unreadable.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            payload = yaml.safe_load(fh)
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def save_profile(path: str, data: dict[str, Any]) -> None:
    """Persist *data* as canonical YAML to *path*.

    Creates parent directories when needed.  Output is always YAML (never JSON)
    so that ``profile_version_from_map`` produces a deterministic hash
    regardless of how the file was previously written.

    Uses an internal serializer that correctly round-trips empty collections
    as ``[]`` / ``{}`` instead of bare ``key:`` (which the project yaml shim
    parses back as ``None``).
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    dumped = "\n".join(_dump_lines(data, 0)) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumped)


def profile_version_from_map(data: dict[str, Any]) -> str:
    """Derive a deterministic version string from a parsed profile dict.

    The version is the full SHA-256 hex digest of the canonical key-sorted
    JSON representation.  This is independent of on-disk formatting (JSON
    vs YAML, whitespace, key ordering).
    """
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Internal YAML serializer — mirrors the project yaml shim's ``_dump_lines``
# but renders empty collections as ``[]`` / ``{}`` so that ``yaml.safe_load``
# round-trips them correctly.
# ---------------------------------------------------------------------------

_YAML_SPECIAL_WORDS = frozenset(
    ("true", "false", "null", "yes", "no", "on", "off")
)
_YAML_SPECIAL_CHARS = set(":#{}[],&*?|>!%@`\"'")


def _dump_scalar(value: object) -> str:
    """Serialize a scalar to a YAML-safe string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        text.lower() in _YAML_SPECIAL_WORDS
        or text != text.strip()
        or any(ch in _YAML_SPECIAL_CHARS for ch in text)
        or not text
        or _looks_numeric(text)
    ):
        return json.dumps(text, ensure_ascii=False)
    return text


def _looks_numeric(text: str) -> bool:
    """Return True if *text* would be parsed as a number by yaml.safe_load."""
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def _dump_lines(value: object, indent: int) -> list[str]:
    """Recursively serialize *value* to a list of YAML lines."""
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}{{}}"]
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{prefix}{key}: {{}}")
                else:
                    lines.append(f"{prefix}{key}:")
                    lines.extend(_dump_lines(item, indent + 2))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}:")
                    lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_dump_scalar(item)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, dict):
                nested = _dump_lines(item, indent + 2)
                if nested:
                    first = nested[0].strip()
                    lines.append(f"{prefix}- {first}")
                    lines.extend(nested[1:])
                else:
                    lines.append(f"{prefix}- {{}}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_dump_scalar(item)}")
        return lines
    return [f"{prefix}{_dump_scalar(value)}"]
