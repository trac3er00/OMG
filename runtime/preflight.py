"""Structured preflight routing for OMG."""
from __future__ import annotations

from runtime.delta_classifier import classify_project_changes
from runtime.tracebank import record_trace
from typing import Any


_HIGH_RISK_DELTA_TOKENS = (
    "auth",
    "payment",
    "billing",
    "checkout",
    "db",
    "database",
    "schema",
    "migration",
    "infra",
    "terraform",
    ".tf",
    "helm",
    "k8s",
    "docker",
    "manifest",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "cargo.toml",
    "go.mod",
    "gemfile",
    "policy",
    "config",
)


def run_preflight(project_dir: str, *, goal: str) -> dict[str, Any]:
    lowered = goal.lower()
    task_class = "implementation"
    risk_class = "medium"
    route = "teams"
    delta = classify_project_changes(project_dir, goal=goal)
    categories = set(delta["categories"])
    requires_security_check = _requires_security_check(delta)
    domain_packs = [category for category in delta["categories"] if category in {"robotics", "vision", "algorithms", "health"}]

    if requires_security_check:
        task_class = "security"
        risk_class = "high"
        route = "security-check"
    elif categories & {"api"} or any(token in lowered for token in ("openapi", "swagger", "postman", "contract", "fixture", "replay")):
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

    trace = record_trace(
        project_dir,
        trace_type="preflight",
        route=route,
        status="ok",
        plan={"goal": goal, "delta_categories": delta["categories"]},
        verify={"risk_class": risk_class},
    )

    return {
        "schema": "PreflightResult",
        "project_dir": project_dir,
        "goal": goal,
        "task_class": task_class,
        "risk_class": risk_class,
        "route": route,
        "requires_security_check": requires_security_check,
        "required_tools": _required_tools(route),
        "required_mcps": ["omg-control"] if route in {"security-check", "api-twin", "crazy"} else [],
        "missing_constraints": [],
        "evidence_plan": _evidence_plan(route),
        "delta_classification": delta,
        "domain_packs": domain_packs,
        "trace": {"trace_id": trace["trace_id"], "path": trace["path"]},
    }


def _requires_security_check(delta: dict[str, Any]) -> bool:
    categories = {str(item).lower() for item in delta.get("categories", [])}
    if categories & {"auth", "payment", "db", "infra", "compliance", "health"}:
        return True

    touched_files = [str(path).lower() for path in delta.get("touched_files", [])]
    for file_path in touched_files:
        if any(token in file_path for token in _HIGH_RISK_DELTA_TOKENS):
            return True
    return False


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
