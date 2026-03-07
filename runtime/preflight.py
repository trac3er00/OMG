"""Structured preflight routing for OMG."""
from __future__ import annotations

from typing import Any


def run_preflight(project_dir: str, *, goal: str) -> dict[str, Any]:
    lowered = goal.lower()
    task_class = "implementation"
    risk_class = "medium"
    route = "teams"

    if any(token in lowered for token in ("openapi", "swagger", "postman", "contract", "fixture", "replay")):
        task_class = "contract"
        route = "api-twin"
    elif any(token in lowered for token in ("auth", "secret", "security", "token", "injection")):
        task_class = "security"
        risk_class = "high"
        route = "security-check"
    elif any(token in lowered for token in ("full stack", "frontend and backend", "dashboard", "orchestrate")):
        task_class = "orchestration"
        risk_class = "high"
        route = "crazy"

    return {
        "schema": "PreflightResult",
        "project_dir": project_dir,
        "goal": goal,
        "task_class": task_class,
        "risk_class": risk_class,
        "route": route,
        "required_tools": _required_tools(route),
        "required_mcps": ["omg-control"] if route in {"security-check", "api-twin", "crazy"} else [],
        "missing_constraints": [],
        "evidence_plan": _evidence_plan(route),
    }


def _required_tools(route: str) -> list[str]:
    return {
        "security-check": ["security"],
        "api-twin": ["api-twin"],
        "crazy": ["teams", "ccg"],
    }.get(route, ["teams"])


def _evidence_plan(route: str) -> list[str]:
    return {
        "security-check": ["security findings", "provenance"],
        "api-twin": ["fixture fidelity", "live verification"],
        "crazy": ["verification output", "evidence pack"],
    }.get(route, ["verification output"])
