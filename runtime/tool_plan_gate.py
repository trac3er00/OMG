from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import json

from runtime.context_engine import ContextEngine
from runtime.compliance_governor import classify_bash_command_mode, evaluate_tool_compliance
from runtime.complexity_scorer import score_complexity
from runtime.release_run_coordinator import (
    get_active_coordinator_run_id,
    is_release_orchestration_active,
    resolve_current_run_id as resolve_coordinator_run_id,
)
from runtime.runtime_contracts import read_run_state
from runtime.test_intent_lock import verify_done_when, verify_lock


_logger = logging.getLogger(__name__)


_TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "context7": ("doc", "docs", "documentation", "library", "api reference", "reference"),
    "websearch": ("search", "research", "latest", "news", "web", "lookup"),
    "omg_security_check": ("security", "scan", "vulnerability", "audit", "auth", "token", "secret"),
    "omg-control": ("policy", "governance", "release", "proof", "control plane"),
}
_MUTATION_TOOLS = frozenset({"write", "edit", "multiedit", "bash"})
_READ_ONLY_BASH_ALLOWLIST = (
    re.compile(r"^python\d?(?:\s+-[vV]{1,2}|\s+--version)(?:\s|$)"),
    re.compile(r"^git\s+status(?:\s|$)"),
    re.compile(r"^gh\s+pr\s+view(?:\s|$)"),
    re.compile(r"^(?:.+\|\s*)?tee\s+/dev/null(?:\s|$)"),
)
_FULLY_QUOTED_PATTERN = re.compile(r"^\s*([\"']).*\1\s*$")

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
    _governance: dict[str, object] = {}
    try:
        governance_raw = score_complexity(normalized_goal).get("governance")
        if isinstance(governance_raw, Mapping):
            _governance = {str(key): value for key, value in governance_raw.items()}
    except Exception as exc:
        _logger.debug("Failed to compute governance payload for tool plan %s: %s", plan_id, exc, exc_info=True)
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
        "governance_payload": _governance,
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


def tool_plan_gate_check(
    project_dir: str,
    run_id: str | None,
    tool: str,
    tool_input: dict[str, object] | None = None,
) -> dict[str, object]:
    effective_run_id = get_active_coordinator_run_id(project_dir=project_dir) or run_id
    if not effective_run_id:
        return {"status": "allowed", "reason": "run_id unavailable; skip tool plan gate"}

    tool_input_obj = tool_input if isinstance(tool_input, dict) else {}
    has_plan = has_tool_plan_for_run(project_dir, effective_run_id)

    context_packet = _resolve_bounded_context_packet(
        project_dir=project_dir,
        run_id=effective_run_id,
        fallback_context=None,
    )
    clarification = _clarification_status(context_packet)
    decision = evaluate_tool_compliance(
        project_dir=project_dir,
        run_id=effective_run_id,
        tool=tool,
        has_tool_plan=has_plan,
        clarification_status=clarification,
        tool_input=tool_input,
    )
    reason = str(decision.get("reason", ""))
    if decision.get("status") == "blocked":
        _persist_gate_error(project_dir, effective_run_id, tool, reason)
        return {
            **decision,
            "run_id": effective_run_id,
            "tool": tool,
        }

    if _is_mutation_capable_tool(tool, tool_input_obj) and not _is_docs_exemption(tool_input_obj):
        lock_id = _extract_lock_id(tool_input_obj)
        lock_verdict = verify_lock(project_dir, run_id=effective_run_id, lock_id=lock_id)
        if lock_verdict.get("status") != "ok":
            return {
                "status": "blocked",
                "authority": "test_intent_lock",
                "reason": "test_intent_lock_required_before_mutation",
                "run_id": effective_run_id,
                "tool": tool,
            }

        if is_release_orchestration_active(project_dir=project_dir):
            return {
                **decision,
                "run_id": effective_run_id,
                "tool": tool,
            }

        metadata = _extract_metadata(tool_input_obj)
        done_when_verdict = verify_done_when(metadata, run_id=effective_run_id)
        if done_when_verdict.get("status") != "ok":
            return {
                "status": "blocked",
                "authority": "done_when",
                "reason": "done_when_required_before_mutation",
                "run_id": effective_run_id,
                "tool": tool,
            }

    return {
        **decision,
        "run_id": effective_run_id,
        "tool": tool,
    }


def governed_tool_plan_gate_check(
    project_dir: str,
    run_id: str | None,
    lane_name: str,
    tool: str,
) -> dict[str, object]:
    decision = tool_plan_gate_check(project_dir=project_dir, run_id=run_id, tool=tool)
    return {
        **decision,
        "lane_name": str(lane_name).strip().lower(),
    }


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
    category = str(score_complexity(goal).get("category", "low"))
    if category == "trivial":
        return "low"
    return category


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


def _clarification_status(context_packet: dict[str, object]) -> dict[str, object]:
    raw = context_packet.get("clarification_status")
    if not isinstance(raw, dict):
        return {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        }
    prompt = str(raw.get("clarification_prompt", "")).strip().replace("\n", " ")
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "requires_clarification": bool(raw.get("requires_clarification") is True),
        "intent_class": str(raw.get("intent_class", "")).strip(),
        "clarification_prompt": prompt,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }


def _is_mutation_capable_tool(tool: str, tool_input: dict[str, object]) -> bool:
    token = str(tool or "").strip().lower()
    if token == "bash":
        command = str(tool_input.get("command", "")).strip()
        lowered = command.lower()
        if _is_allowlisted_read_only_bash(lowered):
            return False
        return classify_bash_command_mode(command) == "mutation"
    return token in _MUTATION_TOOLS


def _is_allowlisted_read_only_bash(command: str) -> bool:
    stripped = command.strip()
    if not stripped:
        return True
    if _FULLY_QUOTED_PATTERN.match(stripped):
        return True
    for pattern in _READ_ONLY_BASH_ALLOWLIST:
        if pattern.search(stripped):
            return True
    return False


def _extract_metadata(tool_input: dict[str, object]) -> dict[str, object]:
    metadata = tool_input.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _extract_lock_id(tool_input: dict[str, object]) -> str | None:
    lock_id = tool_input.get("lock_id")
    if isinstance(lock_id, str) and lock_id.strip():
        return lock_id.strip()
    metadata = _extract_metadata(tool_input)
    metadata_lock_id = metadata.get("lock_id")
    if isinstance(metadata_lock_id, str) and metadata_lock_id.strip():
        return metadata_lock_id.strip()
    return None


def _is_docs_exemption(tool_input: dict[str, object]) -> bool:
    exemption = str(tool_input.get("exemption", "")).strip().lower()
    if exemption == "docs":
        return True
    metadata = _extract_metadata(tool_input)
    if metadata.get("exempt") is True and str(metadata.get("exemption", "")).strip().lower() == "docs":
        return True
    return False
