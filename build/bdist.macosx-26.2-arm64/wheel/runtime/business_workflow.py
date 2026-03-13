from __future__ import annotations

from collections.abc import Iterable
from typing import Any

DEFAULT_WORKFLOW_PATH: tuple[str, ...] = (
    "plan",
    "implement",
    "qa",
    "simulate",
    "final_test",
    "production",
)

_STAGE_ALIASES = {
    "plan": "plan",
    "planning": "plan",
    "implement": "implement",
    "implementation": "implement",
    "build": "implement",
    "qa": "qa",
    "quality": "qa",
    "quality_assurance": "qa",
    "test": "final_test",
    "testing": "final_test",
    "final_test": "final_test",
    "final-testing": "final_test",
    "simulate": "simulate",
    "simulation": "simulate",
    "prod": "production",
    "production": "production",
    "deploy": "production",
}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Iterable):
        items: list[str] = []
        for raw in value:
            if isinstance(raw, str):
                text = raw.strip()
                if text:
                    items.append(text)
        return items
    return []


def _resolve_workflow_path(idea: dict[str, Any]) -> list[str]:
    raw_path = idea.get("workflow") or idea.get("path") or idea.get("delivery_path") or idea.get("workflow_path")
    requested = _as_string_list(raw_path)
    resolved: list[str] = []
    for stage in requested:
        key = _STAGE_ALIASES.get(stage.strip().lower())
        if key and key not in resolved:
            resolved.append(key)
    if not resolved:
        return list(DEFAULT_WORKFLOW_PATH)
    for required in DEFAULT_WORKFLOW_PATH:
        if required not in resolved:
            resolved.append(required)
    return resolved


def build_business_task_plan(idea: dict[str, Any]) -> dict[str, Any]:
    goal = str(idea.get("goal", "")).strip() or "unspecified-goal"
    constraints = _as_string_list(idea.get("constraints", []))
    acceptance = _as_string_list(idea.get("acceptance", []))
    user_instructions = _as_string_list(idea.get("user_instructions", []))
    workflow_path = _resolve_workflow_path(idea)

    # Plan Council extensions
    assumptions = _as_string_list(idea.get("assumptions", []))
    objections = _as_string_list(idea.get("objections", []) or idea.get("dissent", []))
    rollback_plan = _as_string_list(idea.get("rollback_plan", []))
    verification_commands = _as_string_list(idea.get("verification_commands", []))
    evidence_requirements = _as_string_list(idea.get("evidence_requirements", []))
    falsifiability = _as_string_list(idea.get("falsifiability", []))

    tasks: list[dict[str, Any]] = []
    task_id = 1

    if user_instructions:
        for instruction in user_instructions:
            tasks.append(
                {
                    "id": f"T{task_id}",
                    "stage": "plan",
                    "title": "Capture user instruction",
                    "detail": instruction,
                    "source": "user_instructions",
                }
            )
            task_id += 1

    for item in constraints:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "plan",
                "title": "Capture delivery constraint",
                "detail": item,
                "source": "constraints",
            }
        )
        task_id += 1

    if "implement" in workflow_path:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "implement",
                "title": "Implement scoped changes",
                "detail": "Apply changes that satisfy user instructions and follow repository patterns.",
                "source": "workflow",
            }
        )
        task_id += 1

    if "qa" in workflow_path:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "qa",
                "title": "Run QA checks",
                "detail": "Validate behavior against constraints and acceptance criteria.",
                "source": "workflow",
            }
        )
        task_id += 1

    if "simulate" in workflow_path:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "simulate",
                "title": "Simulate delivery scenarios",
                "detail": "Exercise expected paths and edge cases before final testing.",
                "source": "workflow",
            }
        )
        task_id += 1

    for item in acceptance:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "final_test",
                "title": "Validate acceptance criterion",
                "detail": item,
                "source": "acceptance",
            }
        )
        task_id += 1

    if "production" in workflow_path:
        tasks.append(
            {
                "id": f"T{task_id}",
                "stage": "production",
                "title": "Prepare production handoff",
                "detail": "Confirm release readiness, residual risks, and deployment checks.",
                "source": "workflow",
            }
        )

    stage_summaries = []
    for stage in workflow_path:
        stage_tasks = [task for task in tasks if task["stage"] == stage]
        stage_summaries.append(
            {
                "stage": stage,
                "task_count": len(stage_tasks),
                "tasks": stage_tasks,
            }
        )

    return {
        "goal": goal,
        "requested_path": _as_string_list(
            idea.get("workflow") or idea.get("path") or idea.get("delivery_path") or idea.get("workflow_path")
        ),
        "resolved_path": workflow_path,
        "constraints": constraints,
        "acceptance": acceptance,
        "user_instructions": user_instructions,
        "assumptions": assumptions,
        "objections": objections,
        "rollback_plan": rollback_plan,
        "verification_commands": verification_commands,
        "evidence_requirements": evidence_requirements,
        "falsifiability": falsifiability,
        "stages": stage_summaries,
        "task_count": len(tasks),
    }


def build_business_workflow_result(
    *,
    idea: dict[str, Any],
    plan: dict[str, Any],
    execution: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    plan_payload = build_business_task_plan(idea)
    checks_value = verification.get("checks") if isinstance(verification, dict) else None
    checks = checks_value if isinstance(checks_value, list) else []
    checks_ok = bool(checks) and all(isinstance(check, dict) and check.get("passed") is True for check in checks)

    stage_status = {
        "plan": "completed" if plan.get("status") == "planned" else "failed",
        "implement": "completed" if execution.get("status") == "executed" else "failed",
        "qa": "completed" if checks_ok else "failed",
        "simulate": "completed" if checks_ok else "failed",
        "final_test": "completed" if checks_ok else "failed",
        "production": "ready" if checks_ok else "blocked",
    }

    return {
        "goal": plan_payload["goal"],
        "workflow_path": plan_payload["resolved_path"],
        "requested_workflow_path": plan_payload["requested_path"],
        "task_plan": plan_payload,
        "stage_status": [
            {
                "stage": stage,
                "status": stage_status.get(stage, "pending"),
            }
            for stage in plan_payload["resolved_path"]
        ],
        "ready_for_production": checks_ok,
    }
