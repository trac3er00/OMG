# pyright: reportMissingImports=false, reportMissingTypeArgument=false
"""Unified query layer over OMG state data silos.

This module provides a stable interface for querying tool activity, failures,
session health, escalation outcomes, and file-level heatmaps.

Incremental JSONL reading is used for ledger-backed queries. Byte offsets and
incremental aggregates are persisted in `.omg/state/.query-offsets.json`.
"""
from __future__ import annotations

import json
import os
import importlib
from datetime import datetime
from typing import Any

from hooks._common import atomic_json_write

try:
    read_cost_summary = importlib.import_module("hooks._cost_ledger").read_cost_summary
except Exception:
    def read_cost_summary(project_dir: str, time_range=None) -> dict:
        del project_dir
        del time_range
        return {
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "by_tool": {},
            "by_session": {},
            "entry_count": 0,
        }


_TOOL_LEDGER = os.path.join(".omg", "state", "ledger", "tool-ledger.jsonl")
_COST_LEDGER = os.path.join(".omg", "state", "ledger", "cost-ledger.jsonl")
_FAILURE_TRACKER = os.path.join(".omg", "state", "ledger", "failure-tracker.json")
_WORKING_MEMORY = os.path.join(".omg", "state", "working-memory.md")
_OFFSETS_FILE = os.path.join(".omg", "state", ".query-offsets.json")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _join(project_dir: str, rel_path: str) -> str:
    return os.path.join(project_dir, rel_path)


def _load_json(path: str, default: object) -> object:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_offsets(project_dir: str) -> dict:
    path = _join(project_dir, _OFFSETS_FILE)
    data = _load_json(path, {})
    if not isinstance(data, dict):
        return {"queries": {}}
    queries = data.get("queries")
    if not isinstance(queries, dict):
        data["queries"] = {}
    return data


def _save_offsets(project_dir: str, offsets: dict) -> None:
    path = _join(project_dir, _OFFSETS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        atomic_json_write(path, offsets)
    except Exception:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(offsets, f, separators=(",", ":"))
        except Exception:
            pass


def _consume_jsonl(
    project_dir: str,
    query_key: str,
    ledger_rel_path: str,
    initial_state: dict,
    consume_entry,
) -> dict:
    """Read only unread JSONL bytes and update cached aggregate state."""
    offsets = _load_offsets(project_dir)
    query_state = offsets.get("queries", {}).get(query_key, {})
    offset = _safe_int(query_state.get("offset", 0), 0)
    state = query_state.get("state", initial_state)
    if not isinstance(state, dict):
        state = dict(initial_state)

    path = _join(project_dir, ledger_rel_path)
    if not os.path.exists(path):
        offsets.setdefault("queries", {})[query_key] = {
            "offset": 0,
            "state": dict(initial_state),
        }
        _save_offsets(project_dir, offsets)
        return dict(initial_state)

    try:
        size = os.path.getsize(path)
    except OSError:
        return state

    if offset > size:
        offset = 0
        state = dict(initial_state)

    try:
        with open(path, "rb") as f:
            f.seek(offset)
            for raw in f:
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(entry, dict):
                    consume_entry(state, entry)
            new_offset = f.tell()
    except Exception:
        return state

    offsets.setdefault("queries", {})[query_key] = {
        "offset": new_offset,
        "state": state,
    }
    _save_offsets(project_dir, offsets)
    return state


def _entry_success(entry: dict) -> bool:
    tool = str(entry.get("tool", ""))
    if tool == "Bash":
        exit_code = entry.get("exit_code")
        if exit_code is None:
            return True
        return _safe_int(exit_code, 0) == 0
    if tool in ("Write", "Edit", "MultiEdit"):
        if "success" not in entry:
            return True
        return bool(entry.get("success"))
    return True


def _parse_iso_ts(ts: object) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        text = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_test_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    cmd = command.lower()
    markers = (
        "pytest",
        "npm test",
        "pnpm test",
        "yarn test",
        "bun test",
        "go test",
        "cargo test",
        "unittest",
    )
    return any(marker in cmd for marker in markers)


def _ensure_cost_cache(project_dir: str, query_key: str) -> None:
    """Bootstrap cost cache from read_cost_summary once, then read incrementally."""
    path = _join(project_dir, _COST_LEDGER)
    if not os.path.exists(path):
        return

    offsets = _load_offsets(project_dir)
    queries = offsets.setdefault("queries", {})
    if query_key in queries:
        return

    summary = read_cost_summary(project_dir)
    by_tool = {}
    raw_by_tool = summary.get("by_tool", {})
    if isinstance(raw_by_tool, dict):
        for tool, stats in raw_by_tool.items():
            if not isinstance(stats, dict):
                continue
            by_tool[str(tool)] = {
                "token_total": _safe_int(stats.get("tokens", 0), 0),
                "count": _safe_int(stats.get("count", 0), 0),
            }

    state = {
        "tools": by_tool,
        "tokens_used": _safe_int(summary.get("total_tokens", 0), 0),
        "cost_usd": _safe_float(summary.get("total_cost_usd", 0.0), 0.0),
    }
    queries[query_key] = {
        "offset": _safe_int(os.path.getsize(path), 0),
        "state": state,
    }
    _save_offsets(project_dir, offsets)


def get_tool_stats(project_dir: str, hours: int | None = None) -> dict:
    """Return per-tool count, success_rate, and avg_tokens.

    `hours` is currently accepted for API compatibility and ignored.
    """
    del hours

    def consume_tool(state: dict, entry: dict) -> None:
        tool = str(entry.get("tool", "unknown"))
        tools = state.setdefault("tools", {})
        rec = tools.setdefault(tool, {"count": 0, "success": 0})
        rec["count"] = _safe_int(rec.get("count", 0), 0) + 1
        if _entry_success(entry):
            rec["success"] = _safe_int(rec.get("success", 0), 0) + 1

    tool_state = _consume_jsonl(
        project_dir,
        "tool_stats_tool",
        _TOOL_LEDGER,
        {"tools": {}},
        consume_tool,
    )

    _ensure_cost_cache(project_dir, "tool_stats_cost")

    def consume_cost(state: dict, entry: dict) -> None:
        tool = str(entry.get("tool", "unknown"))
        tokens = _safe_int(entry.get("tokens_in", 0), 0) + _safe_int(entry.get("tokens_out", 0), 0)
        tools = state.setdefault("tools", {})
        rec = tools.setdefault(tool, {"token_total": 0, "count": 0})
        rec["token_total"] = _safe_int(rec.get("token_total", 0), 0) + tokens
        rec["count"] = _safe_int(rec.get("count", 0), 0) + 1

    cost_state = _consume_jsonl(
        project_dir,
        "tool_stats_cost",
        _COST_LEDGER,
        {"tools": {}, "tokens_used": 0, "cost_usd": 0.0},
        consume_cost,
    )

    tools = {}
    tool_agg = tool_state.get("tools", {}) if isinstance(tool_state, dict) else {}
    cost_agg = cost_state.get("tools", {}) if isinstance(cost_state, dict) else {}
    names = set(tool_agg.keys()) | set(cost_agg.keys())
    for tool in names:
        counts = tool_agg.get(tool, {})
        token_stats = cost_agg.get(tool, {})
        count = _safe_int(counts.get("count", 0), 0)
        success = _safe_int(counts.get("success", 0), 0)
        token_total = _safe_int(token_stats.get("token_total", 0), 0)
        token_count = _safe_int(token_stats.get("count", 0), 0)
        tools[tool] = {
            "count": count,
            "success_rate": (success / count) if count > 0 else 0.0,
            "avg_tokens": (token_total / token_count) if token_count > 0 else 0.0,
        }
    return tools


def get_failure_hotspots(project_dir: str) -> dict:
    """Return failure patterns with counts, recent errors, and escalation flag."""
    data = _load_json(_join(project_dir, _FAILURE_TRACKER), {})
    if not isinstance(data, dict):
        return {}
    out = {}
    for pattern, details in data.items():
        if not isinstance(details, dict):
            continue
        count = _safe_int(details.get("count", 0), 0)
        errors = details.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        normalized = [str(err) for err in errors if err]
        out[str(pattern)] = {
            "count": count,
            "last_3_errors": normalized[-3:],
            "escalated": count >= 3,
        }
    return out


def get_session_summary(project_dir: str) -> dict:
    """Return session-level aggregate summary across ledgers."""

    def consume_tool(state: dict, entry: dict) -> None:
        state["tool_calls"] = _safe_int(state.get("tool_calls", 0), 0) + 1
        if _entry_success(entry):
            state["success_count"] = _safe_int(state.get("success_count", 0), 0) + 1

        tool = str(entry.get("tool", ""))
        file_path = entry.get("file")
        if tool in ("Write", "Edit", "MultiEdit") and isinstance(file_path, str) and file_path:
            seen = state.setdefault("files_modified_set", [])
            if file_path not in seen:
                seen.append(file_path)

        if tool == "Bash" and _is_test_command(entry.get("command", "")):
            state["tests_run"] = _safe_int(state.get("tests_run", 0), 0) + 1

        ts = _parse_iso_ts(entry.get("ts"))
        if ts is not None:
            first = _parse_iso_ts(state.get("first_ts"))
            last = _parse_iso_ts(state.get("last_ts"))
            if first is None or ts < first:
                state["first_ts"] = ts.isoformat()
            if last is None or ts > last:
                state["last_ts"] = ts.isoformat()

    tool_state = _consume_jsonl(
        project_dir,
        "session_summary_tool",
        _TOOL_LEDGER,
        {
            "tool_calls": 0,
            "success_count": 0,
            "files_modified_set": [],
            "tests_run": 0,
            "first_ts": "",
            "last_ts": "",
        },
        consume_tool,
    )

    _ensure_cost_cache(project_dir, "session_summary_cost")

    def consume_cost(state: dict, entry: dict) -> None:
        tokens = _safe_int(entry.get("tokens_in", 0), 0) + _safe_int(entry.get("tokens_out", 0), 0)
        state["tokens_used"] = _safe_int(state.get("tokens_used", 0), 0) + tokens
        state["cost_usd"] = _safe_float(state.get("cost_usd", 0.0), 0.0) + _safe_float(
            entry.get("cost_usd", 0.0),
            0.0,
        )

    cost_state = _consume_jsonl(
        project_dir,
        "session_summary_cost",
        _COST_LEDGER,
        {"tools": {}, "tokens_used": 0, "cost_usd": 0.0},
        consume_cost,
    )

    tool_calls = _safe_int(tool_state.get("tool_calls", 0), 0)
    success_count = _safe_int(tool_state.get("success_count", 0), 0)
    first_ts = _parse_iso_ts(tool_state.get("first_ts"))
    last_ts = _parse_iso_ts(tool_state.get("last_ts"))
    duration = 0
    if first_ts is not None and last_ts is not None:
        duration = max(0, int((last_ts - first_ts).total_seconds()))

    files_modified = tool_state.get("files_modified_set", [])
    if not isinstance(files_modified, list):
        files_modified = []

    return {
        "duration": duration,
        "tool_calls": tool_calls,
        "success_rate": (success_count / tool_calls) if tool_calls > 0 else 0.0,
        "files_modified": len(files_modified),
        "tests_run": _safe_int(tool_state.get("tests_run", 0), 0),
        "tokens_used": _safe_int(cost_state.get("tokens_used", 0), 0),
        "cost_usd": _safe_float(cost_state.get("cost_usd", 0.0), 0.0),
    }


def get_escalation_effectiveness(project_dir: str) -> dict:
    """Return escalation counts and coarse resolution estimate.

    Escalations are inferred from active failure patterns at count >= 3.
    Resolution is inferred by matching "resolved" mentions in working-memory.
    """
    hotspots = get_failure_hotspots(project_dir)
    escalated_patterns = [name for name, entry in hotspots.items() if bool(entry.get("escalated"))]
    escalations = len(escalated_patterns)

    resolved = 0
    memory_path = _join(project_dir, _WORKING_MEMORY)
    memory_text = ""
    if os.path.exists(memory_path):
        try:
            with open(memory_path, "r", encoding="utf-8", errors="ignore") as f:
                memory_text = f.read().lower()
        except Exception:
            memory_text = ""

    if memory_text:
        for pattern in escalated_patterns:
            compact = pattern.lower()
            if compact in memory_text and "resolved" in memory_text:
                resolved += 1

    unresolved = max(escalations - resolved, 0)
    return {
        "escalations": escalations,
        "resolved": resolved,
        "unresolved": unresolved,
    }


def get_file_heatmap(project_dir: str) -> dict:
    """Return per-file read/write/edit interaction counts."""

    def consume_entry(state: dict, entry: dict) -> None:
        tool = str(entry.get("tool", ""))
        file_path = entry.get("file")
        if not isinstance(file_path, str) or not file_path:
            return
        files = state.setdefault("files", {})
        rec = files.setdefault(file_path, {"reads": 0, "writes": 0, "edits": 0})
        if tool == "Read":
            rec["reads"] = _safe_int(rec.get("reads", 0), 0) + 1
        elif tool == "Write":
            rec["writes"] = _safe_int(rec.get("writes", 0), 0) + 1
        elif tool in ("Edit", "MultiEdit"):
            rec["edits"] = _safe_int(rec.get("edits", 0), 0) + 1

    state = _consume_jsonl(
        project_dir,
        "file_heatmap_tool",
        _TOOL_LEDGER,
        {"files": {}},
        consume_entry,
    )
    files = state.get("files", {}) if isinstance(state, dict) else {}
    if not isinstance(files, dict):
        return {}
    return files


__all__ = [
    "get_tool_stats",
    "get_failure_hotspots",
    "get_session_summary",
    "get_escalation_effectiveness",
    "get_file_heatmap",
]
