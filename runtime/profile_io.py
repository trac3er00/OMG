"""Canonical profile I/O — single owner of profile.yaml read/write/version.

All profile consumers should use this module to load and persist profile data.
``profile_version`` is derived from a canonical key-sorted JSON hash of the
parsed dict, never from raw file text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import yaml


_logger = logging.getLogger(__name__)


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
    except Exception as exc:
        _logger.debug("Failed to load profile from %s: %s", path, exc, exc_info=True)
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


_GOVERNED_SECTIONS = ("style", "safety")
_GOVERNED_CONFIRMATION_STATES = ("confirmed", "pending_confirmation", "inferred")


def classify_preference_section(field: str, value: str) -> str:
    token = f"{field} {value}".lower()
    if "safety" in token or "guardrail" in token or "override" in token:
        return "safety"
    return "style"


def is_destructive_preference(field: str, value: str) -> bool:
    token = f"{field} {value}".lower()
    destructive_tokens = (
        "disable",
        "off",
        "bypass",
        "ignore",
        "override",
        "unsafe",
        "no_guard",
        "no guard",
    )
    return any(piece in token for piece in destructive_tokens)


def ensure_governed_preferences(profile: dict[str, Any]) -> None:
    governed_obj = profile.get("governed_preferences")
    governed = governed_obj if isinstance(governed_obj, dict) else {}
    for section in _GOVERNED_SECTIONS:
        raw_entries = governed.get(section)
        if not isinstance(raw_entries, list):
            governed[section] = []
            continue
        normalized: list[dict[str, Any]] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            entry = _normalize_governed_entry(raw, section)
            if entry is not None:
                normalized.append(entry)
        governed[section] = normalized
    profile["governed_preferences"] = governed


def upsert_governed_preference(
    profile: dict[str, Any],
    *,
    field: str,
    value: str,
    source: str,
    learned_at: str,
    updated_at: str,
    section: str,
    confirmation_state: str,
    decay_metadata: dict[str, Any] | None,
) -> None:
    ensure_governed_preferences(profile)
    governed = profile["governed_preferences"]
    if not isinstance(governed, dict):
        return
    target = governed.get(section)
    if not isinstance(target, list):
        target = []

    match_index = -1
    for idx, raw_entry in enumerate(target):
        if not isinstance(raw_entry, dict):
            continue
        if str(raw_entry.get("field", "")).strip() == field and str(raw_entry.get("value", "")).strip() == value:
            match_index = idx
            break

    baseline: dict[str, Any] = {
        "field": field,
        "value": value,
        "source": source,
        "learned_at": learned_at,
        "updated_at": updated_at,
        "section": section,
        "confirmation_state": confirmation_state,
    }
    if section == "style" and decay_metadata is not None:
        baseline["decay_metadata"] = decay_metadata

    if match_index == -1:
        target.append(baseline)
    else:
        existing = target[match_index]
        if isinstance(existing, dict):
            baseline["learned_at"] = str(existing.get("learned_at", learned_at)).strip() or learned_at
        target[match_index] = baseline

    governed[section] = target


def _normalize_governed_entry(raw: dict[str, Any], section: str) -> dict[str, Any] | None:
    field = str(raw.get("field", "")).strip()
    value = " ".join(str(raw.get("value", "")).strip().split())
    source = str(raw.get("source", "")).strip()
    learned_at = str(raw.get("learned_at", "")).strip()
    updated_at = str(raw.get("updated_at", "")).strip()
    section_raw = str(raw.get("section", section)).strip().lower()
    confirmation_state = str(raw.get("confirmation_state", "")).strip().lower()

    if not (field and value and source and learned_at and updated_at):
        return None
    if section_raw not in _GOVERNED_SECTIONS:
        return None
    if confirmation_state not in _GOVERNED_CONFIRMATION_STATES:
        return None

    out: dict[str, Any] = {
        "field": field,
        "value": value,
        "source": source,
        "learned_at": learned_at,
        "updated_at": updated_at,
        "section": section_raw,
        "confirmation_state": confirmation_state,
    }

    if section_raw == "style" and confirmation_state == "inferred":
        decay_raw = raw.get("decay_metadata")
        decay = decay_raw if isinstance(decay_raw, dict) else {}
        out["decay_metadata"] = {
            "decay_score": _coerce_decay_score(decay.get("decay_score", 0.0)),
            "last_seen_at": str(decay.get("last_seen_at", updated_at)).strip() or updated_at,
            "decay_reason": str(decay.get("decay_reason", "inferred_signal")).strip() or "inferred_signal",
        }
    return out


def _coerce_decay_score(raw: Any) -> float:
    try:
        score = float(raw)
    except (TypeError, ValueError):
        score = 0.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return round(score, 3)


def assess_profile_risk(profile: dict[str, Any]) -> dict[str, Any]:
    governed_obj = profile.get("governed_preferences")
    governed = governed_obj if isinstance(governed_obj, dict) else {}

    style_entries = governed.get("style", [])
    style_entries = style_entries if isinstance(style_entries, list) else []
    safety_entries = governed.get("safety", [])
    safety_entries = safety_entries if isinstance(safety_entries, list) else []

    destructive: list[dict[str, Any]] = []
    pending = 0

    for entry in style_entries + safety_entries:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field", ""))
        value = str(entry.get("value", ""))
        if is_destructive_preference(field, value):
            destructive.append(entry)
        if str(entry.get("confirmation_state", "")).strip() == "pending_confirmation":
            pending += 1

    risk_level = "low"
    if destructive or pending > 0:
        risk_level = "high" if destructive else "medium"

    return {
        "risk_level": risk_level,
        "destructive_entries": destructive,
        "pending_confirmations": pending,
        "requires_review": risk_level in ("medium", "high"),
    }
