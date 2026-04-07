# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

MODES: dict[str, dict[str, object]] = {
    "fast": {
        "primary": "claude-haiku-4-5",
        "description": "Cheapest/fastest",
        "cost_factor": 0.25,
    },
    "balanced": {
        "primary": "claude-sonnet-4",
        "description": "Best balance",
        "cost_factor": 1.0,
    },
    "quality": {
        "primary": "claude-opus-4",
        "description": "Highest quality",
        "cost_factor": 4.0,
    },
}

_current_mode: str = "balanced"


def set_mode(mode: str) -> dict[str, object]:
    global _current_mode
    if mode not in MODES:
        raise ValueError(f"Invalid mode. Choose: {list(MODES.keys())}")
    _current_mode = mode
    return {"mode": mode, **MODES[mode]}


def get_mode() -> str:
    return _current_mode


def get_preferred_model(complexity: str = "medium") -> str:
    return str(MODES[_current_mode]["primary"])
