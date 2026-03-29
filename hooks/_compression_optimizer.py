#!/usr/bin/env python3
"""Compression guideline optimizer from compression feedback JSONL."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

from ._common import get_feature_flag


def _new_guidelines() -> dict[str, object]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "always_keep": [],
        "prefer_keep": [],
        "compress_ok": [],
        "drop_ok": [],
    }


def _is_failure_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("failed") is True:
        return True
    if entry.get("success") is False:
        return True
    status = str(entry.get("status", "")).strip().lower()
    if status in {"failed", "failure", "error"}:
        return True
    outcome = str(entry.get("outcome", "")).strip().lower()
    return outcome in {"failed", "failure", "error"}


def _coerce_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        item = raw.strip()
        if item:
            items.append(item)
    return items


def _extract_dropped_items(entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return []
    for key in ("dropped_items", "dropped", "items_dropped", "dropped_context"):
        items = _coerce_items(entry.get(key))
        if items:
            return items
    return []


def _read_feedback(path: str) -> tuple[Counter[str], set[str]]:
    failure_counts: Counter[str] = Counter()
    all_dropped_items: set[str] = set()

    if not path or not os.path.exists(path):
        return failure_counts, all_dropped_items

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                dropped_items = _extract_dropped_items(entry)
                if not dropped_items:
                    continue

                all_dropped_items.update(dropped_items)
                if _is_failure_entry(entry):
                    failure_counts.update(set(dropped_items))
    except OSError:
        return Counter(), set()

    return failure_counts, all_dropped_items


def optimize_guidelines(feedback_path: str, output_path: str) -> dict[str, object]:
    if not get_feature_flag("CONTEXT_MANAGER", default=False):
        return _new_guidelines()

    guidelines = _new_guidelines()
    failure_counts, all_items = _read_feedback(feedback_path)

    always_keep = sorted(item for item, count in failure_counts.items() if count >= 3)
    prefer_keep = sorted(item for item, count in failure_counts.items() if 1 <= count <= 2)
    compress_ok = sorted(item for item in all_items if failure_counts.get(item, 0) == 0)

    guidelines["always_keep"] = always_keep
    guidelines["prefer_keep"] = prefer_keep
    guidelines["compress_ok"] = compress_ok

    if output_path:
        try:
            parent = os.path.dirname(output_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(guidelines, handle, indent=2)
        except OSError:
            try:
                print(f"[omg:warn] failed to write compression guidelines output: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass

    return guidelines


__all__ = ["optimize_guidelines"]
