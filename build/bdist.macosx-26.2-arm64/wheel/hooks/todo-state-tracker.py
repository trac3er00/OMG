#!/usr/bin/env python3
"""
PostToolUse Hook: Todo State Tracker (v1)

Parses todo lists from agent responses and tracks completion status.
Persists state to .omg/state/todo_progress.json for cross-turn tracking.

Feature flag: OMG_TODO_TRACKING_ENABLED (default: False)
"""
import json
import sys
import os
import re
from datetime import datetime, timezone

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import (
    setup_crash_handler,
    json_input,
    get_project_dir,
    get_feature_flag,
    atomic_json_write,
)

setup_crash_handler("todo-state-tracker", fail_closed=False)

# Feature flag check
if not get_feature_flag("TODO_TRACKING", default=False):
    sys.exit(0)

data = json_input()

# Extract response text from various possible fields
response_text = ""
if isinstance(data, dict):
    # PostToolUse hook may have response in different fields
    response_text = (
        data.get("response", "")
        or data.get("tool_response", "")
        or data.get("message", "")
        or ""
    )
    if isinstance(response_text, dict):
        response_text = response_text.get("content", "")

if not isinstance(response_text, str):
    response_text = str(response_text) if response_text else ""

# Parse todo items: regex pattern for markdown todo format
# Matches: - [ ] task text or - [x] task text
TODO_PATTERN = r'- \[([ x])\] (.+)'
matches = re.findall(TODO_PATTERN, response_text, re.IGNORECASE)

if not matches:
    # No todos found, exit cleanly
    sys.exit(0)

# Separate incomplete and complete items
incomplete_items = []
complete_items = []

for status, task_text in matches:
    task_text = task_text.strip()
    if status.lower() == 'x':
        complete_items.append(task_text)
    else:
        incomplete_items.append(task_text)

# Load existing state
project_dir = get_project_dir()
state_path = os.path.join(project_dir, ".omg", "state", "todo_progress.json")

existing_state = {}
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            existing_state = json.load(f)
    except Exception:
        existing_state = {}

# Ensure existing_state is a dict
if not isinstance(existing_state, dict):
    existing_state = {}

# Cross-turn merge strategy:
# - Keep existing complete items (don't regress)
# - Add new complete items
# - Update incomplete items (replace with current turn's findings)
# - Preserve session_id if available

merged_complete = list(set(existing_state.get("complete", []) + complete_items))
merged_incomplete = incomplete_items  # Replace with current turn's findings

# Build new state
new_state = {
    "incomplete": merged_incomplete,
    "complete": merged_complete,
    "total": len(merged_incomplete) + len(merged_complete),
    "last_updated": datetime.now(timezone.utc).isoformat(),
}

# Preserve session_id if available
if "session_id" in existing_state:
    new_state["session_id"] = existing_state["session_id"]
elif "session_id" in data:
    new_state["session_id"] = data.get("session_id")

# Atomically write state
atomic_json_write(state_path, new_state)

sys.exit(0)
