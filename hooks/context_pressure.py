#!/usr/bin/env python3
"""Context pressure estimation - importable module for OMG hooks."""

import json
import os
from datetime import datetime, timezone

_DEFAULT_THRESHOLD = 150


def estimate_context_pressure(project_dir):
    threshold = _DEFAULT_THRESHOLD
    try:
        settings_path = os.path.join(project_dir, "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
            threshold = settings.get("_oal", {}).get("context_budget", {}).get(
                "pressure_threshold", _DEFAULT_THRESHOLD
            )
    except Exception:
        pass

    tool_count = 0
    ledger_path = os.path.join(project_dir, ".omg", "state", "ledger", "tool-ledger.jsonl")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8", errors="ignore") as ledger_file:
                for line in ledger_file:
                    if line.strip():
                        tool_count += 1
        except Exception:
            pass

    is_high = tool_count >= threshold

    try:
        pressure_path = os.path.join(project_dir, ".omg", "state", ".context-pressure.json")
        os.makedirs(os.path.dirname(pressure_path), exist_ok=True)
        with open(pressure_path, "w", encoding="utf-8") as pressure_file:
            json.dump(
                {
                    "tool_count": tool_count,
                    "threshold": threshold,
                    "is_high": is_high,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
                pressure_file,
            )
    except Exception:
        pass

    return tool_count, threshold, is_high
