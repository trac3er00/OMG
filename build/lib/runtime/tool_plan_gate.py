from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import json


_TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "context7": ("doc", "docs", "documentation", "library", "api reference", "reference"),
    "websearch": ("search", "research", "latest", "news", "web", "lookup"),
    "omg_security_check": ("security", "scan", "vulnerability", "audit", "auth", "token", "secret"),
    "omg-control": ("policy", "governance", "release", "proof", "control plane"),
}


def build_tool_plan(
    goal: str,
    available_tools: list[str],
    context_packet: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_goal = str(goal or "").strip()
    normalized_tools = _normalize_tools(available_tools)

    selected_tools: list[dict[str, object]] = []
    for tool_name in normalized_tools:
        if _is_tool_needed(tool_name, normalized_goal):
            selected_tools.append(
                {
                    "name": tool_name,
                    "args": _default_args(tool_name, normalized_goal, context_packet),
                    "rationale": _rationale(tool_name),
                }
            )

    if not selected_tools and normalized_tools:
        fallback = normalized_tools[0]
        selected_tools.append(
            {
                "name": fallback,
                "args": _default_args(fallback, normalized_goal, context_packet),
                "rationale": "fallback: no explicit keyword match; keep single minimal tool",
            }
        )

    run_id = resolve_current_run_id(project_dir=None)
    plan_id = _new_plan_id(run_id=run_id)
    payload: dict[str, object] = {
        "plan_id": plan_id,
        "goal": normalized_goal,
        "tools": selected_tools,
        "budget_estimate": {
            "estimated_calls": len(selected_tools),
            "estimated_context_chars": _estimate_context_chars(context_packet),
            "goal_complexity": _goal_complexity(normalized_goal),
        },
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _persist_plan(_project_dir(), plan_id, payload)
    return payload


def resolve_current_run_id(project_dir: str | None = None) -> str | None:
    run_id = str(os.environ.get("OMG_RUN_ID", "")).strip()
    if run_id:
        return run_id

    root = _project_dir(project_dir)
    active_run = root / ".omg" / "shadow" / "active-run"
    if not active_run.exists():
        return None
    try:
        value = active_run.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def has_tool_plan_for_run(project_dir: str, run_id: str | None) -> bool:
    if not run_id:
        return False
    plans_dir = Path(project_dir) / ".omg" / "state" / "tool_plans"
    if not plans_dir.exists():
        return False
    run_prefix = _safe_token(run_id)
    return any(plans_dir.glob(f"{run_prefix}-plan-*.json"))


def tool_plan_gate_check(project_dir: str, run_id: str | None, tool: str) -> dict[str, object]:
    if not run_id:
        return {"status": "allowed", "reason": "run_id unavailable; skip tool plan gate"}
    if has_tool_plan_for_run(project_dir, run_id):
        return {"status": "allowed", "reason": "tool plan present", "run_id": run_id}

    reason = "tool plan required before mutation-capable MCP evaluation"
    _persist_gate_error(project_dir, run_id, tool, reason)
    return {"status": "blocked", "reason": reason, "run_id": run_id, "tool": tool}


def _normalize_tools(available_tools: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw_name in available_tools:
        name = str(raw_name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        output.append(name)
    return output


def _is_tool_needed(tool_name: str, goal: str) -> bool:
    lowered_tool = tool_name.lower()
    lowered_goal = goal.lower()
    keywords = _TOOL_KEYWORDS.get(lowered_tool, ())
    return any(token in lowered_goal for token in keywords)


def _default_args(tool_name: str, goal: str, context_packet: dict[str, object] | None) -> dict[str, object]:
    if tool_name == "context7":
        return {"query": goal}
    if tool_name == "websearch":
        return {"query": goal, "numResults": 5}
    if tool_name == "omg_security_check":
        return {"scope": ".", "include_live_enrichment": False}
    if tool_name == "omg-control":
        return {"query": goal}

    context_hint = ""
    if isinstance(context_packet, dict):
        context_hint = str(context_packet.get("summary", ""))[:120]
    if context_hint:
        return {"goal": goal, "context_hint": context_hint}
    return {"goal": goal}


def _rationale(tool_name: str) -> str:
    return f"selected '{tool_name}' because goal requires matched capability"


def _estimate_context_chars(context_packet: dict[str, object] | None) -> int:
    if not isinstance(context_packet, dict):
        return 0
    summary = str(context_packet.get("summary", ""))
    return len(summary)


def _goal_complexity(goal: str) -> str:
    length = len(goal.split())
    if length >= 25:
        return "high"
    if length >= 10:
        return "medium"
    return "low"


def _new_plan_id(run_id: str | None) -> str:
    if run_id:
        return f"{_safe_token(run_id)}-plan-{uuid4().hex[:10]}"
    return f"plan-{uuid4().hex[:12]}"


def _project_dir(project_dir: str | None = None) -> Path:
    if project_dir:
        return Path(project_dir)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _persist_plan(project_dir: Path, plan_id: str, payload: dict[str, object]) -> None:
    plans_dir = project_dir / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / f"{plan_id}.json"
    _atomic_write_json(path, payload)


def _persist_gate_error(project_dir: str, run_id: str, tool: str, reason: str) -> None:
    plans_dir = Path(project_dir) / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / f"{run_id}-gate-error.json"
    payload = {
        "status": "blocked",
        "run_id": run_id,
        "tool": tool,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(path, payload)


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    _ = temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    _ = os.replace(temp_path, path)


def _safe_token(value: str) -> str:
    chars = [ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip()]
    token = "".join(chars).strip("-")
    return token or "run"
