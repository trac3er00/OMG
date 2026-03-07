#!/usr/bin/env python3
"""
IntentGate Keyword Detection Hook — OMG v1.2

UserPromptSubmit hook that detects magic keywords in user prompts,
maps them to intents with confidence scoring, and injects a LEADER_HINT
into the hook output for downstream routing. Detection only — no execution.

Classification v1.2:
  - Each detected intent includes a confidence score (0.0–1.0)
  - Compound intent parsing: multiple keywords → multiple intents

Confidence rules:
  - Exact keyword match (standalone): 0.95
  - Keyword embedded in context: 0.90
  - Keyword in compound phrase (multi-intent): 0.85
  - Multiple occurrences of same keyword: 0.98 (cap)

Magic keywords:
  - ultrawork, autopilot, ralph → execution modes
  - plan this, tdd, search → task types
  - stop, crazy → special directives
"""
import json
import sys
import os
import re
import time

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

try:
    from hooks._common import (
        setup_crash_handler,
        json_input,
        get_feature_flag,
        _resolve_project_dir,
        check_performance_budget,
        PRE_TOOL_INJECT_MAX_MS,
    )
except ImportError:
    import importlib
    _common = importlib.import_module("_common")
    setup_crash_handler = _common.setup_crash_handler
    json_input = _common.json_input
    get_feature_flag = _common.get_feature_flag
    _resolve_project_dir = _common._resolve_project_dir
    check_performance_budget = _common.check_performance_budget
    PRE_TOOL_INJECT_MAX_MS = _common.PRE_TOOL_INJECT_MAX_MS

setup_crash_handler("intentgate-keyword-detector", fail_closed=False)

# ═══════════════════════════════════════════════════════════
# KEYWORD → INTENT MAPPING
# ═══════════════════════════════════════════════════════════
KEYWORD_INTENT_MAP = {
    "ultrawork": "INTENT_MAX_EFFORT",
    "autopilot": "INTENT_AUTONOMOUS",
    "ralph": "INTENT_LOOP",
    "plan this": "INTENT_PLAN",
    "tdd": "INTENT_TEST_DRIVEN",
    "search": "INTENT_SEARCH",
    "stop": "INTENT_STOP",
    "crazy": "INTENT_CRAZY",
}


# ═══════════════════════════════════════════════════════════
# CONFIDENCE SCORING ENGINE
# ═══════════════════════════════════════════════════════════

def _count_keyword_occurrences(keyword, prompt_lower):
    """Count occurrences of keyword in prompt (respecting matching rules)."""
    if " " in keyword:
        # Multi-word: non-overlapping substring count
        count = 0
        start = 0
        while True:
            idx = prompt_lower.find(keyword, start)
            if idx == -1:
                break
            count += 1
            start = idx + len(keyword)
        return count
    else:
        # Single-word: word boundary count
        pattern = r'\b' + re.escape(keyword) + r'\b'
        return len(re.findall(pattern, prompt_lower))


def _compute_confidence(keyword, prompt_lower, occurrence_count, total_intents):
    """Compute confidence score for a detected intent.

    Rules (applied in priority order):
      - Multiple occurrences of same keyword: 0.98 (capped)
      - Keyword in compound phrase (multiple intents): 0.85
      - Exact keyword match (standalone prompt): 0.95
      - Keyword embedded in context signals: 0.90
    """
    # Multiple occurrences of same keyword → highest confidence (cap)
    if occurrence_count > 1:
        return 0.98

    # Compound intent (multiple different keywords detected)
    if total_intents > 1:
        return 0.85

    # Single intent, single occurrence
    stripped = prompt_lower.strip()

    # Exact/standalone match → high confidence
    if stripped == keyword:
        return 0.95

    # Keyword embedded in surrounding context → slightly lower
    return 0.90
# ═══════════════════════════════════════════════════════════
# FEATURE FLAG CHECK
# ═══════════════════════════════════════════════════════════
start_time = time.time()

if not get_feature_flag("INTENTGATE", default=False):
    # Feature disabled — return no-op JSON
    json.dump({}, sys.stdout)
    sys.exit(0)

# ═══════════════════════════════════════════════════════════
# INPUT PARSING
# ═══════════════════════════════════════════════════════════
data = json_input()

prompt = data.get("tool_input", {}).get("user_message", "") or data.get("user_message", "")
if not prompt:
    json.dump({}, sys.stdout)
    sys.exit(0)

prompt_lower = prompt.lower().strip()

# ═══════════════════════════════════════════════════════════
# KEYWORD DETECTION (case-insensitive, multi-keyword, confidence scoring)
# ═══════════════════════════════════════════════════════════

# First pass: detect keywords with occurrence counts
detected_raw = []

for keyword, intent in KEYWORD_INTENT_MAP.items():
    occurrences = _count_keyword_occurrences(keyword, prompt_lower)
    if occurrences > 0:
        detected_raw.append((keyword, intent, occurrences))

# Second pass: compute confidence scores
num_intents = len(detected_raw)
detected_intents = []

for keyword, intent, occurrences in detected_raw:
    confidence = _compute_confidence(keyword, prompt_lower, occurrences, num_intents)
    detected_intents.append({
        "intent": intent,
        "confidence": confidence,
        "keyword": keyword,
    })
# ═══════════════════════════════════════════════════════════
# OUTPUT CONSTRUCTION
# ═══════════════════════════════════════════════════════════
output = {}

if detected_intents:
    # Inject LEADER_HINT with detected intents and confidence scores
    output["LEADER_HINT"] = {
        "detected_intents": detected_intents,
        "keyword_count": len(detected_intents),
        "routing_enabled": True,
        "classification_version": "1.2",
    }

# ═══════════════════════════════════════════════════════════
# PERFORMANCE BUDGET CHECK
# ═══════════════════════════════════════════════════════════
elapsed_ms = (time.time() - start_time) * 1000
check_performance_budget("intentgate-keyword-detector", elapsed_ms, PRE_TOOL_INJECT_MAX_MS)

# ═══════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════
json.dump(output, sys.stdout)
sys.exit(0)
