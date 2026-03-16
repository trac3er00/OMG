#!/usr/bin/env python3
"""PostToolUse budget governor (BATS-style additionalContext injection)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any

HOOKS_DIR = os.path.dirname(__file__)


def _load_module(module_name: str, filename: str):
    path = os.path.join(HOOKS_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_common = _load_module("_common", "_common.py")
_cost_ledger = _load_module("_cost_ledger", "_cost_ledger.py")
_token_counter = _load_module("_token_counter", "_token_counter.py")

get_feature_flag = _common.get_feature_flag
get_project_dir = _common.get_project_dir
json_input = _common.json_input
setup_crash_handler = _common.setup_crash_handler
read_cost_summary = _cost_ledger.read_cost_summary
estimate_tokens = _token_counter.estimate_tokens

DEFAULT_SESSION_LIMIT_USD = 5.0
DEFAULT_INPUT_PER_MTOK = 3.0
DEFAULT_OUTPUT_PER_MTOK = 15.0
DEFAULT_PROJECTED_TOOL_CALLS = 50
DEFAULT_THRESHOLDS = [50, 80, 95]
THRESHOLD_STATE_FILE = ".omg/state/.cost-threshold-state.json"


def _safe_float(value, default: float) -> float:
    try:
        parsed = float(value)
        if parsed <= 0:
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def _read_budget_config(project_dir: str) -> tuple[float, float, float]:
    session_limit = DEFAULT_SESSION_LIMIT_USD
    input_per_mtok = DEFAULT_INPUT_PER_MTOK
    output_per_mtok = DEFAULT_OUTPUT_PER_MTOK

    settings_path = os.path.join(project_dir, "settings.json")
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        budget_cfg = settings.get("_omg", {}).get("cost_budget", {})
        pricing = budget_cfg.get("pricing", {})
        session_limit = _safe_float(budget_cfg.get("session_limit_usd"), DEFAULT_SESSION_LIMIT_USD)
        input_per_mtok = _safe_float(pricing.get("input_per_mtok"), DEFAULT_INPUT_PER_MTOK)
        output_per_mtok = _safe_float(pricing.get("output_per_mtok"), DEFAULT_OUTPUT_PER_MTOK)
    except Exception:
        pass

    return session_limit, input_per_mtok, output_per_mtok


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    except Exception:
        return str(value)


def _estimate_call_cost(tool_input, tool_response, input_per_mtok: float, output_per_mtok: float) -> float:
    input_text = _to_text(tool_input)
    output_text = _to_text(tool_response)

    tokens_in = estimate_tokens(input_text, tier=2)
    tokens_out = estimate_tokens(output_text, tier=2)

    cost_in = (tokens_in / 1_000_000.0) * input_per_mtok
    cost_out = (tokens_out / 1_000_000.0) * output_per_mtok
    return max(0.0, cost_in + cost_out)


def _project_total_calls(used_cost_usd: float, used_calls: int, session_limit_usd: float) -> int:
    if used_calls <= 0 or used_cost_usd <= 0:
        return DEFAULT_PROJECTED_TOOL_CALLS
    avg_cost = used_cost_usd / float(used_calls)
    if avg_cost <= 0:
        return DEFAULT_PROJECTED_TOOL_CALLS
    projected = max(used_calls, int(round(session_limit_usd / avg_cost)))
    if projected > (DEFAULT_PROJECTED_TOOL_CALLS * 10):
        return DEFAULT_PROJECTED_TOOL_CALLS
    rounded = int(round(projected / 10.0) * 10)
    return max(10, rounded)


def _build_context(used_cost_usd: float, session_limit_usd: float, used_calls: int, projected_calls: int) -> str:
    remaining_ratio = 1.0 - (used_cost_usd / session_limit_usd)
    remaining_pct = int(round(max(0.0, min(1.0, remaining_ratio)) * 100))
    return (
        f"Budget: {remaining_pct}% remaining | "
        f"${used_cost_usd:.2f} of ${session_limit_usd:.2f} used | "
        f"{used_calls} tool calls of ~{projected_calls}"
    )


def _get_threshold_message(pct: int) -> str:
    if pct >= 95:
        return (
            f"@cost-limit: {pct}% budget used. "
            "Complete current task and stop. Do NOT start new tasks."
        )
    if pct >= 80:
        return (
            f"@cost-critical: {pct}% budget used. "
            "Be efficient \u2014 minimize unnecessary tool calls, "
            "batch operations where possible."
        )
    return f"@cost-warning: {pct}% budget used"


def _read_thresholds_config(project_dir: str) -> list[int]:
    try:
        settings_path = os.path.join(project_dir, "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        raw = settings.get("_omg", {}).get("cost_budget", {}).get("thresholds")
        if isinstance(raw, list) and all(isinstance(t, (int, float)) for t in raw):
            return sorted(int(t) for t in raw)
    except Exception:
        pass
    return list(DEFAULT_THRESHOLDS)


def _read_threshold_state(project_dir: str) -> dict[str, Any]:
    path = os.path.join(project_dir, THRESHOLD_STATE_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"session_id": "", "fired": []}


def _write_threshold_state(project_dir: str, state: dict[str, Any]) -> None:
    path = os.path.join(project_dir, THRESHOLD_STATE_FILE)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, separators=(",", ":"))
    except Exception:
        pass


def _check_thresholds(
    used_pct: float, project_dir: str, session_id: str
) -> list[str]:
    thresholds = _read_thresholds_config(project_dir)
    state = _read_threshold_state(project_dir)

    if state.get("session_id", "") != session_id:
        state = {"session_id": session_id, "fired": []}

    already_fired = set(state.get("fired", []))
    new_messages: list[str] = []
    new_fired: list[int] = []

    for threshold in thresholds:
        if used_pct >= threshold and threshold not in already_fired:
            new_messages.append(_get_threshold_message(threshold))
            new_fired.append(threshold)

    if new_fired:
        state["fired"] = sorted(list(already_fired | set(new_fired)))
        state["session_id"] = session_id
        _write_threshold_state(project_dir, state)

    return new_messages


def _check_budget_envelope(project_dir: str) -> str:
    run_id = os.environ.get("OMG_RUN_ID", "").strip()
    if not run_id:
        return ""
    try:
        parent = os.path.dirname(HOOKS_DIR)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        from runtime.budget_envelopes import get_budget_envelope_manager

        mgr = get_budget_envelope_manager(project_dir)
        result = mgr.check_envelope(run_id)
        if result.status == "ok":
            return ""
        action_tag = {"warn": "@envelope-warning", "reflect": "@envelope-critical", "block": "@envelope-limit"}
        tag = action_tag.get(result.governance_action, "@envelope-warning")
        return f"{tag}: {result.reason} [action={result.governance_action}]"
    except Exception:
        return ""


def main() -> None:
    setup_crash_handler("budget-governor", fail_closed=False)

    payload = json_input()
    if not get_feature_flag("COST_TRACKING", default=False):
        sys.exit(0)

    project_dir = get_project_dir()
    session_limit_usd, input_per_mtok, output_per_mtok = _read_budget_config(project_dir)
    summary = read_cost_summary(project_dir)

    estimated_current_cost = _estimate_call_cost(
        payload.get("tool_input", {}),
        payload.get("tool_response", {}),
        input_per_mtok,
        output_per_mtok,
    )

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    by_session = summary.get("by_session", {})

    if session_id and session_id in by_session:
        session_data = by_session[session_id]
        used_cost_usd = float(session_data.get("cost_usd", 0.0)) + estimated_current_cost
        used_calls = int(session_data.get("count", 0)) + 1
        provenance = "session"
    else:
        used_cost_usd = float(summary.get("total_cost_usd", 0.0)) + estimated_current_cost
        used_calls = int(summary.get("entry_count", 0)) + 1
        provenance = "default"

    projected_calls = _project_total_calls(used_cost_usd, used_calls, session_limit_usd)

    context = _build_context(
        used_cost_usd=used_cost_usd,
        session_limit_usd=session_limit_usd,
        used_calls=used_calls,
        projected_calls=projected_calls,
    )

    used_pct = (used_cost_usd / session_limit_usd * 100) if session_limit_usd > 0 else 0.0
    threshold_alerts = _check_thresholds(used_pct, project_dir, session_id)
    if threshold_alerts:
        context += "\n" + "\n".join(threshold_alerts)

    envelope_context = _check_budget_envelope(project_dir)
    if envelope_context:
        context += "\n" + envelope_context

    json.dump({"additionalContext": context, "provenance": provenance}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
