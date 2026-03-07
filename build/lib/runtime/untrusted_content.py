"""State and provenance tracking for untrusted external content."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


STATE_REL_PATH = Path(".omg") / "state" / "untrusted-content.json"
_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"\b(system|assistant|developer)\s*:", re.IGNORECASE),
    re.compile(r"\b(run|execute|commit|push|apply_patch|edit)\b", re.IGNORECASE),
)


def mark_untrusted_content(
    project_dir: str,
    *,
    source_type: str,
    content: str,
    source_ref: str = "",
) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    state = get_untrusted_content_state(project_dir)
    sanitized, quarantined = quarantine_instruction_like_text(content)
    entry = {
        "source_type": source_type,
        "source_ref": source_ref,
        "quarantined_fragments": quarantined,
        "trust_score": 0.0,
    }
    provenance = list(state.get("provenance", []))
    provenance.append(entry)
    next_state = {
        "active": True,
        "last_source_type": source_type,
        "last_source_ref": source_ref,
        "sanitized_content": sanitized,
        "quarantined_fragments": quarantined,
        "provenance": provenance[-20:],
        "trust_scores": {"external_content": 0.0},
    }
    _write_state(state_path, next_state)
    return next_state


def clear_untrusted_content(project_dir: str, *, reason: str) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    existing = get_untrusted_content_state(project_dir)
    next_state = {
        **existing,
        "active": False,
        "cleared_reason": reason,
    }
    _write_state(state_path, next_state)
    return next_state


def get_untrusted_content_state(project_dir: str) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    if not state_path.exists():
        return {
            "active": False,
            "provenance": [],
            "trust_scores": {},
        }
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "active": False,
            "provenance": [],
            "trust_scores": {},
        }
    return payload if isinstance(payload, dict) else {"active": False, "provenance": [], "trust_scores": {}}


def is_untrusted_content_mode_active(project_dir: str) -> bool:
    return bool(get_untrusted_content_state(project_dir).get("active", False))


def quarantine_instruction_like_text(content: str) -> tuple[str, list[str]]:
    sanitized_lines: list[str] = []
    quarantined: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if any(pattern.search(line) for pattern in _INSTRUCTION_PATTERNS):
            quarantined.append(raw_line)
            continue
        sanitized_lines.append(raw_line)
    return "\n".join(sanitized_lines).strip(), quarantined


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / STATE_REL_PATH


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
