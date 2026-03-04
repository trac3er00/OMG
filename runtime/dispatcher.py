"""Runtime dispatch orchestration for OAL v1 adapters."""
from __future__ import annotations

from typing import Any

from runtime.adapters import get_adapters
from runtime.business_workflow import build_business_workflow_result


def dispatch_runtime(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    adapters = get_adapters()
    adapter = adapters.get(runtime)
    if adapter is None:
        return {
            "status": "error",
            "error_code": "RUNTIME_NOT_FOUND",
            "runtime": runtime,
            "message": f"Unknown runtime: {runtime}",
        }

    try:
        plan = adapter.plan(idea)
        execution = adapter.execute(plan)
        verification = adapter.verify(execution)
        evidence = adapter.collect_evidence(verification)
        business_workflow = build_business_workflow_result(
            idea=idea,
            plan=plan,
            execution=execution,
            verification=verification,
        )
        return {
            "status": "ok",
            "runtime": runtime,
            "plan": plan,
            "execution": execution,
            "verification": verification,
            "evidence": evidence,
            "business_workflow": business_workflow,
        }
    except Exception as exc:  # pragma: no cover - defensive guard
        return {
            "status": "error",
            "error_code": "RUNTIME_EXECUTION_FAILED",
            "runtime": runtime,
            "message": str(exc),
        }
