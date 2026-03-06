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


def _as_string_map(value: Any, keys: tuple[str, ...]) -> dict[str, list[str]]:
    normalized = {key: [] for key in keys}
    if not isinstance(value, dict):
        return normalized
    for key in keys:
        normalized[key] = _as_string_list(value.get(key, []))
    return normalized


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


def _build_failure_taxonomy(provider_execution: dict[str, Any], checks: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    smoke_status = str(provider_execution.get("smoke_status", "")).strip().lower()
    if smoke_status and smoke_status != "success":
        failures.append(f"provider_{smoke_status}")
    for check in checks:
        if isinstance(check, dict) and check.get("passed") is not True:
            failures.append(f"check_{check.get('name', 'unknown')}")
    return failures


def build_business_task_plan(idea: dict[str, Any]) -> dict[str, Any]:
    goal = str(idea.get("goal", "")).strip() or "unspecified-goal"
    constraints = _as_string_list(idea.get("constraints", []))
    acceptance = _as_string_list(idea.get("acceptance", []))
    user_instructions = _as_string_list(idea.get("user_instructions", []))
    workflow_path = _resolve_workflow_path(idea)

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
    failed_checks = [
        str(check.get("name", "unknown"))
        for check in checks
        if isinstance(check, dict) and check.get("passed") is not True
    ]
    passed_checks = [
        str(check.get("name", "unknown"))
        for check in checks
        if isinstance(check, dict) and check.get("passed") is True
    ]
    provider_execution = idea.get("provider_execution") if isinstance(idea.get("provider_execution"), dict) else {}
    provider_smoke_status = str(provider_execution.get("smoke_status", "")).strip().lower()
    provider_degraded = bool(provider_smoke_status and provider_smoke_status != "success")
    verification_state = "verified" if checks_ok else ("failed" if checks else "unverified")
    if provider_degraded and checks_ok:
        verification_state = "degraded"

    verification_summary = {
        "state": verification_state,
        "check_count": len(checks),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "provider_degraded": provider_degraded,
        "provider_smoke_status": provider_smoke_status or None,
    }
    evidence_requirements = _as_string_map(
        idea.get("evidence_required"),
        ("tests", "security_scans", "reproducibility", "artifacts"),
    )

    stage_status = {
        "plan": "completed" if plan.get("status") == "planned" else "failed",
        "implement": "completed" if execution.get("status") == "executed" else "failed",
        "qa": "completed" if checks_ok else "failed",
        "simulate": "completed" if checks_ok else "failed",
        "final_test": "completed" if checks_ok else "failed",
        "production": "ready" if checks_ok else "blocked",
    }
    if verification_state == "degraded":
        stage_status["qa"] = "degraded"
        stage_status["simulate"] = "degraded"
        stage_status["final_test"] = "degraded"
        stage_status["production"] = "blocked"

    failure_taxonomy = _build_failure_taxonomy(provider_execution, checks)
    qualification = {
        "schema": "OmgModelFactoryQualification",
        "workflow_depth": len(plan_payload["resolved_path"]),
        "replayable": True,
        "long_horizon_ready": verification_state == "verified" and not failure_taxonomy,
        "failure_taxonomy": failure_taxonomy,
    }

    return {
        "goal": plan_payload["goal"],
        "workflow_path": plan_payload["resolved_path"],
        "requested_workflow_path": plan_payload["requested_path"],
        "task_plan": plan_payload,
        "verification_summary": verification_summary,
        "provider_execution": dict(provider_execution),
        "evidence_requirements": evidence_requirements,
        "qualification": qualification,
        "stage_status": [
            {
                "stage": stage,
                "status": stage_status.get(stage, "pending"),
            }
            for stage in plan_payload["resolved_path"]
        ],
        "ready_for_production": verification_state == "verified",
    }
