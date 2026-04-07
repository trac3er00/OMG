from __future__ import annotations

import importlib.metadata
import json
import os
import time
from collections.abc import Mapping
from typing import NotRequired, TypedDict, cast


HANDOFF_PATH = os.path.join(".omg", "state", "handoff-latest.json")
STALENESS_DAYS = 7


class ResumeResult(TypedDict):
    available: bool
    state: dict[str, object] | None
    reason: NotRequired[str]
    version: NotRequired[str | None]
    age_hours: NotRequired[float]


class HandoffRecord(TypedDict):
    version: str
    saved_at: float
    state: dict[str, object]


def save_handoff(state: dict[str, object]) -> None:
    try:
        version = importlib.metadata.version("oh-my-god")
    except Exception:
        version = "3.0.0"

    record: HandoffRecord = {
        "version": version,
        "saved_at": time.time(),
        "state": state,
    }
    os.makedirs(os.path.dirname(HANDOFF_PATH), exist_ok=True)
    with open(HANDOFF_PATH, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)


def check_resume() -> ResumeResult:
    if not os.path.exists(HANDOFF_PATH):
        return {"available": False, "state": None, "reason": "no_handoff_found"}

    try:
        with open(HANDOFF_PATH, encoding="utf-8") as handle:
            raw_record = cast(object, json.load(handle))
    except Exception as exc:
        return {"available": False, "state": None, "reason": f"parse_error: {exc}"}

    if not isinstance(raw_record, Mapping):
        return {
            "available": False,
            "state": None,
            "reason": "parse_error: handoff record must be an object",
        }

    record = cast(Mapping[str, object], raw_record)

    state = record.get("state", {})
    if not isinstance(state, dict):
        state = {}

    version = record.get("version")
    if not isinstance(version, str):
        version = None

    saved_at_raw = record.get("saved_at", 0.0)
    saved_at = float(saved_at_raw) if isinstance(saved_at_raw, (int, float)) else 0.0

    age_days = (time.time() - saved_at) / 86400
    if age_days > STALENESS_DAYS:
        return {
            "available": False,
            "state": None,
            "reason": f"stale: {age_days:.1f} days old",
        }

    return {
        "available": True,
        "state": cast(dict[str, object], state),
        "version": version,
        "age_hours": age_days * 24,
    }


def clear_handoff() -> None:
    if os.path.exists(HANDOFF_PATH):
        os.remove(HANDOFF_PATH)
