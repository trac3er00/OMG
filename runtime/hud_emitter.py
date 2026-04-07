"""HUD event emitter — writes structured events to JSONL for the enhanced HUD."""

from __future__ import annotations

import json
import os
import time

HUD_EVENTS_PATH = os.path.join(".omg", "state", "hud-events.jsonl")


def emit_event(event_type: str, data: dict) -> None:
    """Write HUD telemetry event to JSONL file."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        "data": data,
    }
    os.makedirs(os.path.dirname(HUD_EVENTS_PATH), exist_ok=True)
    with open(HUD_EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def emit_agent_start(agent_id: str, task: str) -> None:
    emit_event("agent_start", {"agent_id": agent_id, "task": task})


def emit_agent_stop(agent_id: str, result: str) -> None:
    emit_event("agent_stop", {"agent_id": agent_id, "result": result})


def emit_cost_update(tokens: int, usd: float, budget_remaining_pct: float) -> None:
    emit_event(
        "cost_update",
        {
            "tokens": tokens,
            "usd": usd,
            "budget_remaining_pct": budget_remaining_pct,
        },
    )


def emit_phase_change(phase: str, detail: str = "") -> None:
    emit_event("phase_change", {"phase": phase, "detail": detail})
