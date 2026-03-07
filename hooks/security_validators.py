"""Shared validation helpers for security-sensitive filesystem and config writes."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


_OPAQUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_opaque_identifier(value: str, field_name: str, max_length: int = 64) -> str:
    """Validate an opaque identifier used in filenames or paths."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid {field_name}: must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"Invalid {field_name}: value is required")
    if len(normalized) > max_length:
        raise ValueError(f"Invalid {field_name}: exceeds {max_length} characters")
    if ".." in normalized or not _OPAQUE_IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid {field_name}: use only ASCII letters, numbers, dot, underscore, and dash"
        )
    return normalized


def ensure_path_within_dir(base_dir: str | Path, candidate_path: str | Path) -> str:
    """Return a resolved path and reject traversal outside the intended base directory."""
    base = Path(base_dir).resolve(strict=False)
    candidate = Path(candidate_path).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Resolved path escapes base directory: {candidate}") from exc
    return str(candidate)


def validate_server_name(server_name: str, max_length: int = 64) -> str:
    """Validate an MCP server identifier suitable for JSON keys and TOML table names."""
    if not isinstance(server_name, str):
        raise ValueError("Invalid server_name: must be a string")

    normalized = server_name.strip()
    if not normalized:
        raise ValueError("Invalid server_name: value is required")
    if len(normalized) > max_length:
        raise ValueError(f"Invalid server_name: exceeds {max_length} characters")
    if not _SERVER_NAME_RE.fullmatch(normalized):
        raise ValueError("Invalid server_name: use only ASCII letters, numbers, underscore, and dash")
    return normalized


def validate_server_url(server_url: str) -> str:
    """Validate an MCP server URL and reject newline/control injection."""
    if not isinstance(server_url, str):
        raise ValueError("Invalid server_url: must be a string")

    normalized = server_url.strip()
    if not normalized:
        raise ValueError("Invalid server_url: value is required")
    if "\n" in normalized or "\r" in normalized:
        raise ValueError("Invalid server_url: newline characters are not allowed")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid server_url: must be an http or https URL")
    return normalized


def toml_quote_string(value: str) -> str:
    """Escape TOML basic string content."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
