#!/usr/bin/env python3
"""
Magic Keyword Router — OMG v1.2

PostToolUse hook that reads the LEADER_HINT produced by
intentgate-keyword-detector, selects the appropriate agent based on intent,
and writes a routing result to `.omg/state/routing_result.json`.

Decision only — no subprocess calls or agent execution.

Input sources (checked in priority order):
  1. LEADER_HINT in stdin JSON (from hook pipeline)
  2. `.omg/state/leader_hint.json` (persisted by future integrations)

Feature flag: OMG_MAGIC_ROUTER_ENABLED (default off)
"""
import json
import os
import sys
import time

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

try:
    from hooks._common import (
        setup_crash_handler,
        json_input,
        get_feature_flag,
        atomic_json_write,
        get_project_dir,
        check_performance_budget,
        PRE_TOOL_INJECT_MAX_MS,
    )
except ImportError:
    import importlib
    _common = importlib.import_module("_common")
    setup_crash_handler = _common.setup_crash_handler
    json_input = _common.json_input
    get_feature_flag = _common.get_feature_flag
    atomic_json_write = _common.atomic_json_write
    get_project_dir = _common.get_project_dir
    check_performance_budget = _common.check_performance_budget
    PRE_TOOL_INJECT_MAX_MS = _common.PRE_TOOL_INJECT_MAX_MS

try:
    from hooks._agent_registry import INTENT_ROUTING
except ImportError:
    _registry = importlib.import_module("_agent_registry")
    INTENT_ROUTING = _registry.INTENT_ROUTING

setup_crash_handler("magic-keyword-router", fail_closed=False)

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════
ROUTING_RESULT_PATH = ".omg/state/routing_result.json"
LEADER_HINT_PATH = ".omg/state/leader_hint.json"


# ═══════════════════════════════════════════════════════════
# FEATURE FLAG CHECK
# ═══════════════════════════════════════════════════════════
start_time = time.time()

if not get_feature_flag("MAGIC_ROUTER", default=False):
    # Feature disabled — no-op
    json.dump({}, sys.stdout)
    sys.exit(0)

# ═══════════════════════════════════════════════════════════
# INPUT PARSING
# ═══════════════════════════════════════════════════════════
data = json_input()


def _extract_leader_hint(hook_data):
    """Extract LEADER_HINT from hook stdin data.

    Checks multiple locations where the hint may appear:
      - Top-level "LEADER_HINT" key
      - Nested under "tool_output"
      - Nested under "hookSpecificOutput"
    """
    if not isinstance(hook_data, dict):
        return None
    # Direct top-level
    hint = hook_data.get("LEADER_HINT")
    if hint:
        return hint
    # Nested in tool_output
    tool_output = hook_data.get("tool_output", {})
    if isinstance(tool_output, dict):
        hint = tool_output.get("LEADER_HINT")
        if hint:
            return hint
    # Nested in hookSpecificOutput
    hso = hook_data.get("hookSpecificOutput", {})
    if isinstance(hso, dict):
        hint = hso.get("LEADER_HINT")
        if hint:
            return hint
    return None


def _read_leader_hint_file(project_dir):
    """Read LEADER_HINT from persisted file (secondary source)."""
    path = os.path.join(project_dir, LEADER_HINT_PATH)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # File may contain {"LEADER_HINT": {...}} or the hint directly
        if isinstance(data, dict):
            return data.get("LEADER_HINT", data) if "detected_intents" not in data else data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_routing(leader_hint):
    """Given a LEADER_HINT dict, resolve the target agent.

    Returns (target_agent, intent, confidence) tuple.
    target_agent may be None (e.g., INTENT_STOP → halt).
    """
    detected = leader_hint.get("detected_intents", [])
    if not detected:
        return None, None, 0.0

    # Pick first non-None routable intent (highest priority = first in list)
    for intent_entry in detected:
        intent_name = intent_entry.get("intent", "")
        confidence = intent_entry.get("confidence", 0.0)
        target = INTENT_ROUTING.get(intent_name)

        # INTENT_STOP maps to None explicitly — that IS a valid routing result
        if intent_name in INTENT_ROUTING:
            return target, intent_name, confidence

    # No known intent found
    return None, None, 0.0


# ═══════════════════════════════════════════════════════════
# LEADER_HINT RESOLUTION (stdin preferred, file fallback)
# ═══════════════════════════════════════════════════════════
project_dir = get_project_dir()
leader_hint = _extract_leader_hint(data)

if leader_hint is None:
    leader_hint = _read_leader_hint_file(project_dir)

# ═══════════════════════════════════════════════════════════
# ROUTING DECISION
# ═══════════════════════════════════════════════════════════
from datetime import datetime, timezone

routing_result_path = os.path.join(project_dir, ROUTING_RESULT_PATH)
ts = datetime.now(timezone.utc).isoformat()

if leader_hint and leader_hint.get("detected_intents"):
    target_agent, intent, confidence = _resolve_routing(leader_hint)
    routing_result = {
        "target_agent": target_agent,
        "intent": intent,
        "confidence": confidence,
        "fallback": False,
        "timestamp": ts,
    }
else:
    # No LEADER_HINT → fallback
    routing_result = {
        "target_agent": None,
        "intent": None,
        "confidence": 0.0,
        "fallback": True,
        "timestamp": ts,
    }

atomic_json_write(routing_result_path, routing_result)

# ═══════════════════════════════════════════════════════════
# PERFORMANCE BUDGET CHECK
# ═══════════════════════════════════════════════════════════
elapsed_ms = (time.time() - start_time) * 1000
check_performance_budget("magic-keyword-router", elapsed_ms, PRE_TOOL_INJECT_MAX_MS)

# ═══════════════════════════════════════════════════════════
# OUTPUT (no-op for PostToolUse — just exit clean)
# ═══════════════════════════════════════════════════════════
json.dump({}, sys.stdout)
sys.exit(0)
