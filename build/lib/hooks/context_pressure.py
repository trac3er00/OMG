#!/usr/bin/env python3
"""Context pressure estimation - importable module for OMG hooks."""

import json
import os
from datetime import datetime, timezone

try:
    from runtime.context_limits import get_model_limits, compaction_trigger
except Exception:
    get_model_limits = None
    compaction_trigger = None


def _detect_model_id(context_packet=None):
    for key in ("CLAUDE_MODEL", "OMG_MODEL_ID", "OPENAI_MODEL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value

    if isinstance(context_packet, dict):
        model = context_packet.get("model")
        if isinstance(model, dict):
            for key in ("id", "display_name", "name"):
                value = str(model.get(key, "") or "").strip()
                if value:
                    return value
        elif isinstance(model, str) and model.strip():
            return model.strip()
    return ""


def _host_aware_threshold(context_packet=None):
    model_id = _detect_model_id(context_packet)
    if compaction_trigger is not None and get_model_limits is not None:
        return int(compaction_trigger(model_id)), model_id, get_model_limits(model_id)
    return 80_000, model_id, {"class_label": "128k-class"}


def estimate_context_pressure(project_dir, context_packet=None):
    threshold, model_id, limits = _host_aware_threshold(context_packet)
    try:
        settings_path = os.path.join(project_dir, "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
            configured = settings.get("_omg", {}).get("context_budget", {}).get(
                "pressure_threshold", threshold
            )
            threshold = int(configured)
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
                    "model_id": model_id,
                    "class_label": limits.get("class_label", "128k-class"),
                    "is_high": is_high,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
                pressure_file,
            )
    except Exception:
        pass

    return tool_count, threshold, is_high
