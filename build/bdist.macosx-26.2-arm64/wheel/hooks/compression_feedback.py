#!/usr/bin/env python3
"""PostToolUseFailure Hook — Acon-style compression feedback loop."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

HOOKS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(HOOKS_DIR)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from hooks._common import atomic_json_write, get_feature_flag, get_project_dir, json_input, setup_crash_handler


setup_crash_handler("compression-feedback", fail_closed=False)

MAX_BYTES = 5 * 1024 * 1024
PROMOTION_THRESHOLD = 3
POST_COMPACTION_WINDOW = timedelta(minutes=30)


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _extract_failure_reason(payload: dict[str, Any]) -> str:
    for key in ("error", "message", "failure_reason"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    tool_response = payload.get("tool_response")
    if isinstance(tool_response, dict):
        for key in ("error", "message", "stderr", "stdout"):
            val = tool_response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:500]
    elif isinstance(tool_response, str) and tool_response.strip():
        return tool_response.strip()[:500]

    return "unknown"


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def _read_last_compaction_ts(state_dir: str) -> datetime | None:
    data = _read_json(os.path.join(state_dir, "last-compaction.json"))
    if not data:
        return None
    for key in ("timestamp", "ts", "compacted_at", "last_compaction"):
        parsed = _parse_iso8601(data.get(key))
        if parsed:
            return parsed
    return None


def _read_handoff_snapshot(state_dir: str) -> str:
    handoff_path = os.path.join(state_dir, "handoff.md")
    try:
        with open(handoff_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:4000]
    except Exception:
        return ""


def _candidate_items(context_snapshot: str) -> list[str]:
    items: list[str] = []
    for raw_line in context_snapshot.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        if line and not line.startswith("#"):
            items.append(line)
    return items


def _match_dropped_items(payload: dict[str, Any], context_snapshot: str) -> list[str]:
    if not context_snapshot:
        return []
    haystack = " ".join(
        [
            json.dumps(payload.get("tool_input", ""), sort_keys=True),
            json.dumps(payload.get("tool_response", ""), sort_keys=True),
            str(payload.get("error", "")),
            str(payload.get("message", "")),
        ]
    ).lower()

    matched = []
    for item in _candidate_items(context_snapshot):
        token = item.strip().lower()
        if token and token in haystack:
            matched.append(item)
    return sorted(set(matched))


def _rotate_jsonl_if_needed(path: str) -> None:
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
            archive = path + ".1"
            if os.path.exists(archive):
                try:
                    os.remove(archive)
                except OSError:
                    pass
            shutil.move(path, archive)
    except Exception:
        pass


def _read_feedback_entries(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def _append_jsonl(path: str, entry: dict[str, Any]) -> None:
    try:
        import fcntl

        fd = open(path, "a", encoding="utf-8")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(json.dumps(entry, separators=(",", ":")) + "\n")
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()
    except (ImportError, BlockingIOError):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except Exception:
            pass
    except Exception:
        pass


def _promotions(entries: list[dict[str, Any]], matched_items: list[str]) -> list[str]:
    promoted: list[str] = []
    for item in matched_items:
        count = 0
        for row in entries:
            row_items = row.get("matched_items", [])
            if isinstance(row_items, list) and item in row_items:
                count += 1
        if count >= PROMOTION_THRESHOLD:
            promoted.append(item)
    return sorted(set(promoted))


def _update_always_keep(state_dir: str, promoted_items: list[str]) -> None:
    if not promoted_items:
        return
    path = os.path.join(state_dir, "always-keep.json")
    current = _read_json(path) or {}
    existing = current.get("items", [])
    if not isinstance(existing, list):
        existing = []
    merged = sorted(set(str(x) for x in existing if x) | set(promoted_items))
    atomic_json_write(path, {"items": merged})


def main() -> None:
    data = json_input()

    if not get_feature_flag("CONTEXT_MANAGER", default=False):
        sys.exit(0)

    project_dir = get_project_dir()
    state_dir = os.path.join(project_dir, ".omg", "state")
    os.makedirs(state_dir, exist_ok=True)

    compaction_ts = _read_last_compaction_ts(state_dir)
    failure_ts = _parse_iso8601(data.get("timestamp")) or datetime.now(timezone.utc)
    if not compaction_ts:
        sys.exit(0)

    delta = failure_ts - compaction_ts
    post_compaction = timedelta(0) <= delta <= POST_COMPACTION_WINDOW
    if not post_compaction:
        sys.exit(0)

    feedback_path = os.path.join(state_dir, "compression-feedback.jsonl")
    context_snapshot = _read_handoff_snapshot(state_dir)
    matched_items = _match_dropped_items(data, context_snapshot)

    _rotate_jsonl_if_needed(feedback_path)
    prior_entries = _read_feedback_entries(feedback_path)

    provisional_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": str(data.get("session_id", "")),
        "tool_name": str(data.get("tool_name", "")),
        "failure_reason": _extract_failure_reason(data),
        "post_compaction": True,
        "context_snapshot": context_snapshot,
        "promoted_items": [],
        "matched_items": matched_items,
    }

    all_entries = prior_entries + [provisional_entry]
    promoted_items = _promotions(all_entries, matched_items)
    provisional_entry["promoted_items"] = promoted_items

    _append_jsonl(feedback_path, provisional_entry)
    _update_always_keep(state_dir, promoted_items)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
