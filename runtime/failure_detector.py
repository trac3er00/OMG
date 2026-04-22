"""Failure signal detectors for steering-aware command flows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def detect_loop(actions: list[Any], threshold: int = 3) -> bool:
    """Return True when the same action repeats consecutively."""
    if threshold <= 1:
        return bool(actions)

    streak = 0
    previous: Any = object()

    for action in actions:
        if action == previous:
            streak += 1
        else:
            previous = action
            streak = 1

        if streak >= threshold:
            return True

    return False


def detect_cost_spike(
    current_cost: float,
    expected_cost: float,
    multiplier: float = 2.0,
) -> bool:
    """Return True when current cost exceeds the expected multiplier."""
    if multiplier <= 0:
        return False
    if expected_cost <= 0:
        return current_cost > 0
    return current_cost >= expected_cost * multiplier


def detect_stuck(progress_history: list[Any], window: int = 5) -> bool:
    """Return True when recent progress has effectively flatlined."""
    if window <= 1:
        return False
    if len(progress_history) < window:
        return False

    recent = progress_history[-window:]
    if all(item == recent[0] for item in recent):
        return True

    numeric_window = _as_numeric_window(recent)
    if numeric_window is None:
        return False
    return max(numeric_window) == min(numeric_window)


def _as_numeric_window(values: Sequence[Any]) -> list[float] | None:
    numeric_values: list[float] = []
    for value in values:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric_values.append(float(value))
            continue
        try:
            numeric_values.append(float(str(value)))
        except (TypeError, ValueError):
            return None
    return numeric_values


__all__ = ["detect_loop", "detect_cost_spike", "detect_stuck"]
