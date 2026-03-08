from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import json

from runtime.context_engine import ContextEngine
from runtime.release_run_coordinator import resolve_current_run_id as resolve_coordinator_run_id
from runtime.runtime_contracts import read_run_state


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
    run_id: str | None = None,
) -> dict[str, object]:
    normalized_goal = str(goal or "").strip()
    normalized_tools = _normalize_tools(available_tools)
    canonical_run_id = run_id or resolve_current_run_id(project_dir=None)
    bounded_context = _resolve_bounded_context_packet(
        project_dir=str(_project_dir()),
        run_id=canonical_run_id,
        fallback_context=context_packet,
    )
    council = _read_council_verdicts(str(_project_dir()), canonical_run_id)

    selected_tools: list[dict[str, object]] = []
    for tool_name in normalized_tools:
        if _is_tool_needed(tool_name, normalized_goal):
            selected_tools.append(
                {
                    "name": tool_name,
                    "args": _default_args(tool_name, normalized_goal, bounded_context),
                    "rationale": _rationale(tool_name),
                }
            )

    if not selected_tools and normalized_tools:
        fallback = normalized_tools[0]
        selected_tools.append(
            {
                "name": fallback,
                "args": _default_args(fallback, normalized_goal, bounded_context),
                "rationale": "fallback: no explicit keyword match; keep single minimal tool",
            }
        )

    selected_tools = _apply_context_optimization(selected_tools, bounded_context, council)
    plan_id = _new_plan_id(run_id=canonical_run_id)
    payload: dict[str, object] = {
        "plan_id": plan_id,
        "goal": normalized_goal,
        "tools": selected_tools,
        "budget_estimate": {
            "estimated_calls": len(selected_tools),
            "estimated_context_chars": _estimate_context_chars(bounded_context),
            "goal_complexity": _goal_complexity(normalized_goal),
        },
        "context_packet": bounded_context,
        "council_verdicts": council.get("verdicts", {}),
        "run_id": canonical_run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _persist_plan(_project_dir(), plan_id, payload)
    return payload


def resolve_current_run_id(project_dir: str | None = None) -> str | None:
    run_id = resolve_coordinator_run_id(project_dir=project_dir)
    return run_id or None


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
        council = _read_council_verdicts(project_dir, run_id)
        verdict = _council_gate_verdict(council)
        if verdict["blocked"]:
            reason = str(verdict["reason"])
            _persist_gate_error(project_dir, run_id, tool, reason)
            return {
                "status": "blocked",
                "reason": reason,
                "run_id": run_id,
                "tool": tool,
                "council_verdicts": council.get("verdicts", {}),
            }
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


def journal_mutation_bash(
    project_dir: str,
    command: str,
    run_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object] | None:
    try:
        from runtime.interaction_journal import InteractionJournal
        from runtime.rollback_manifest import classify_side_effect
    except ImportError:
        return None

    canonical_run_id = run_id or resolve_current_run_id(project_dir)
    if not canonical_run_id:
        return None

    meta: dict[str, object] = dict(metadata or {})
    meta["command"] = command
    meta["run_id"] = canonical_run_id

    side_effect = classify_side_effect("bash", meta)
    meta["side_effect_scope"] = str(side_effect.get("category", "unknown"))
    meta["side_effect_classification"] = side_effect

    journal = InteractionJournal(project_dir)
    return journal.record_step("bash", meta)


def _safe_token(value: str) -> str:
    chars = [ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip()]
    token = "".join(chars).strip("-")
    return token or "run"


def _resolve_bounded_context_packet(
    *,
    project_dir: str,
    run_id: str | None,
    fallback_context: dict[str, object] | None,
) -> dict[str, object]:
    if run_id:
        packet = ContextEngine(project_dir).build_packet(run_id=run_id, delta_only=True)
        if isinstance(fallback_context, dict) and str(fallback_context.get("summary", "")).strip():
            summary = str(packet.get("summary", "")).strip()
            if not summary or summary == "no context signals available":
                packet["summary"] = str(fallback_context.get("summary", ""))
        return packet
    return dict(fallback_context or {"summary": "", "artifact_pointers": []})


def _read_council_verdicts(project_dir: str, run_id: str | None) -> dict[str, object]:
    if not run_id:
        return {}
    payload = read_run_state(project_dir, "council_verdicts", run_id)
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _council_gate_verdict(council: dict[str, object]) -> dict[str, object]:
    verdicts = council.get("verdicts")
    if not isinstance(verdicts, dict):
        return {"blocked": False, "reason": ""}

    for critic_name, critic_payload in verdicts.items():
        if not isinstance(critic_payload, dict):
            continue
        token = str(critic_payload.get("verdict", "")).strip().lower()
        if token == "fail":
            return {
                "blocked": True,
                "reason": f"council critic '{critic_name}' failed; block mutation-capable tool execution",
            }
    return {"blocked": False, "reason": ""}


def _apply_context_optimization(
    tools: list[dict[str, object]],
    context_packet: dict[str, object],
    council: dict[str, object],
) -> list[dict[str, object]]:
    if len(tools) <= 1:
        return tools

    budget = context_packet.get("budget")
    used_chars = 0
    max_chars = 0
    if isinstance(budget, dict):
        try:
            used_chars = int(budget.get("used_chars", 0))
            max_chars = int(budget.get("max_chars", 0))
        except (TypeError, ValueError):
            used_chars = 0
            max_chars = 0

    verdicts = council.get("verdicts")
    evidence_warn = False
    if isinstance(verdicts, dict):
        evidence = verdicts.get("evidence_completeness")
        if isinstance(evidence, dict):
            evidence_warn = str(evidence.get("verdict", "")).strip().lower() in {"warn", "fail"}

    pressure_high = max_chars > 0 and used_chars >= int(max_chars * 0.9)
    if pressure_high or evidence_warn:
        return tools[:1]
    return tools
