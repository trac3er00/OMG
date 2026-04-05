#!/usr/bin/env python3
"""PreToolUse Hook — Injects plan reminder before each tool call.

Inspired by planning-with-files: forces re-read of plan on every tool call.
OMG version: lighter — checklist-aware, tool-filtered, max 200 chars.
Only injects for mutation tools (Write/Edit/Bash), not read-only tools.
"""
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, get_feature_flag, _resolve_project_dir
from state_migration import resolve_state_file

setup_crash_handler("pre-tool-inject")

MAX_INJECTION = 200  # Total injection budget (chars)

# Read-only tools that don't need plan reminders
READ_ONLY_TOOLS = {
    'Read', 'Glob', 'Grep', 'LS', 'NotebookRead', 'WebFetch', 'WebSearch',
    'TodoRead', 'mcp__filesystem__read_file', 'mcp__filesystem__list_directory',
}


def should_inject(tool_name):
    """Return True if this tool call should get a plan reminder."""
    if not tool_name:
        return True  # unknown tool → inject (safe default)
    return tool_name not in READ_ONLY_TOOLS


def get_checklist_progress(checklist_path):
    """Return (done, total, first_pending) from checklist file."""
    if not os.path.exists(checklist_path):
        return None, None, None
    try:
        with open(checklist_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        total = sum(1 for l in lines if re.search(r'^\s*-\s*\[[ x!]\]', l))
        done = sum(1 for l in lines if re.search(r'^\s*-\s*\[x\]', l, re.IGNORECASE))
        # Find first pending item text
        first_pending = None
        for l in lines:
            if re.search(r'^\s*-\s*\[ \]', l):
                first_pending = re.sub(r'^\s*-\s*\[ \]\s*', '', l).strip()[:50]
                break
        return done, total, first_pending
    except OSError:
        return None, None, None


data = json_input()

if not get_feature_flag("planning_enforcement"):
    sys.exit(0)

# Tool filtering: skip injection for read-only tools
tool_name = data.get("tool_name") if isinstance(data, dict) else None
if not should_inject(tool_name):
    sys.exit(0)

project_dir = _resolve_project_dir()

# Try to find _plan.md
plan_path = resolve_state_file(project_dir, "state/_plan.md", "_plan.md")

if not os.path.exists(plan_path):
    sys.exit(0)

try:
    # Check for checklist progress
    checklist_path = resolve_state_file(project_dir, "state/_checklist.md", "_checklist.md")
    done, total, first_pending = get_checklist_progress(checklist_path)

    if total is not None and total > 0:
        # Checklist-aware format
        reminder = f"{done}/{total} done"
        if first_pending:
            reminder += f" | Next: {first_pending}"
        injection = f"@plan-reminder: {reminder}"[:MAX_INJECTION]
    else:
        # Fallback: first 15 lines of plan
        with open(plan_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[:15]
        head = "".join(lines)[:MAX_INJECTION]
        injection = f"@plan-reminder: {head}"[:MAX_INJECTION]

    json.dump({"contextInjection": injection}, sys.stdout)
except Exception:
    try:
        import sys; print(f"[omg:warn] [pre-tool-inject] failed to build plan reminder: {sys.exc_info()[1]}", file=sys.stderr)
    except Exception:
        pass

sys.exit(0)
