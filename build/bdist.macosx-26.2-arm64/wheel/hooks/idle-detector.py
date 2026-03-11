#!/usr/bin/env python3
"""
Stop Hook: Idle Detector (v1)

Detects when an agent has gone idle with incomplete todos.
Reads .omg/state/todo_progress.json (from todo-state-tracker)
and writes continuation signal to .omg/state/idle_signal.json.

Detection only — does not block the stop.

Feature flag: OMG_IDLE_DETECTION_ENABLED (default: False)
"""
import json
import sys
import os
from datetime import datetime, timezone

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import (  # noqa: E402
    setup_crash_handler,
    json_input,
    get_project_dir,
    get_feature_flag,
    atomic_json_write,
)

setup_crash_handler("idle-detector", fail_closed=False)

# Feature flag check — exit cleanly if disabled
if not get_feature_flag("IDLE_DETECTION", default=False):
    sys.exit(0)

# Consume stdin (stop hooks receive JSON input)
_data = json_input()

project_dir = get_project_dir()
todo_path = os.path.join(project_dir, ".omg", "state", "todo_progress.json")
signal_path = os.path.join(project_dir, ".omg", "state", "idle_signal.json")


def _write_signal(idle: bool, incomplete: list | None = None, call_count: int = 0):
    """Write idle signal state atomically."""
    items = incomplete or []
    atomic_json_write(signal_path, {
        "idle_detected": idle,
        "incomplete_count": len(items),
        "incomplete_items": items[:3],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "stop_hook",
        "call_count": call_count,
    })


# --- Read todo progress ---
todo_state = None
if os.path.exists(todo_path):
    try:
        with open(todo_path, "r", encoding="utf-8") as f:
            todo_state = json.load(f)
    except Exception:
        todo_state = None

# No todo file or malformed → not idle
if not isinstance(todo_state, dict):
    _write_signal(False)
    sys.exit(0)

incomplete = todo_state.get("incomplete", [])
if not isinstance(incomplete, list):
    incomplete = []

# No incomplete items → not idle
if not incomplete:
    _write_signal(False)
    sys.exit(0)

# --- Check call counter from existing signal ---
call_count = 0
if os.path.exists(signal_path):
    try:
        with open(signal_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if isinstance(existing, dict):
            call_count = existing.get("call_count", 0)
    except Exception:
        call_count = 0

# Idle = incomplete todos AND hook has been called at least once before
idle_detected = call_count >= 1

_write_signal(idle_detected, incomplete, call_count + 1)
sys.exit(0)
