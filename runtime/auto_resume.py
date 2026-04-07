from __future__ import annotations

import importlib.metadata
import json
import os
import time
from collections.abc import Callable, Mapping
from typing import NotRequired, TypedDict, cast


HANDOFF_PATH = os.path.join(".omg", "state", "handoff-latest.json")
STALENESS_DAYS = 7
DEFAULT_MAX_RETRIES = 3


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


class HandoffBudgetExceeded(Exception):
    """Raised when a handoff retry budget is exhausted."""


class RetryBudget:
    """Tracks retry attempts and token cost to prevent infinite loops."""

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        self.max_retries = max_retries
        self.attempt_count = 0
        self.token_cost_per_attempt: list[int] = []
        self.success: bool = False

    def increment(self, token_cost: int = 0) -> bool:
        self.attempt_count += 1
        self.token_cost_per_attempt.append(token_cost)
        return self.attempt_count <= self.max_retries

    def diagnostic(self) -> str:
        total = sum(self.token_cost_per_attempt)
        return (
            f"Handoff failed after {self.attempt_count} attempts "
            f"(max: {self.max_retries}). Total token cost: {total}"
        )

    @property
    def health_metrics(self) -> dict[str, object]:
        total_tokens = sum(self.token_cost_per_attempt)
        waste = sum(self.token_cost_per_attempt[:-1]) if self.success else total_tokens
        return {
            "success": self.success,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "token_waste": waste,
            "success_rate": (
                1.0 / self.attempt_count
                if self.success and self.attempt_count > 0
                else 0.0
            ),
        }


def compact_context_for_retry(state: dict[str, object]) -> dict[str, object]:
    compacted: dict[str, object] = {}
    for key, value in state.items():
        if isinstance(value, list) and len(value) > 10:
            compacted[key] = value[-10:]
        elif isinstance(value, str) and len(value) > 2000:
            compacted[key] = value[:2000]
        else:
            compacted[key] = value
    compacted["_compacted"] = True
    return compacted


def resume_with_retries(
    state: dict[str, object],
    handler: Callable[[dict[str, object]], dict[str, object]] | None = None,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    estimate_token_cost: Callable[[dict[str, object]], int] | None = None,
) -> dict[str, object]:
    budget = RetryBudget(max_retries=max_retries)

    _handler: Callable[[dict[str, object]], dict[str, object]]
    if handler is None:
        _handler = lambda s: {"resumed": True, **s}
    else:
        _handler = handler

    _estimate: Callable[[dict[str, object]], int]
    if estimate_token_cost is None:
        _estimate = lambda s: len(json.dumps(s, default=str))
    else:
        _estimate = estimate_token_cost

    current_state = state

    while True:
        cost = _estimate(current_state)
        if not budget.increment(token_cost=cost):
            raise HandoffBudgetExceeded(budget.diagnostic())

        try:
            result = _handler(current_state)
            budget.success = True
            result["_health_metrics"] = budget.health_metrics
            return result
        except HandoffBudgetExceeded:
            raise
        except Exception:
            current_state = compact_context_for_retry(current_state)


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
