"""Runtime dispatch orchestration for OMG v1 adapters."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from runtime.adapters import get_adapters
from runtime.business_workflow import build_business_workflow_result

RUNTIME_DISPATCH_SCHEMA = "OmgRuntimeDispatch"
EVIDENCE_PACK_SCHEMA = "OmgEvidencePack"
LONG_HORIZON_SIMULATION_SCHEMA = "OmgLongHorizonSimulation"


def _build_failure_taxonomy(idea: dict[str, Any], verification: dict[str, Any]) -> list[str]:
    provider_execution = _normalize_provider_execution(idea)
    failures: list[str] = []
    smoke_status = str(provider_execution.get("smoke_status", "")).strip().lower()
    if smoke_status and smoke_status != "success":
        failures.append(f"provider_{smoke_status}")
    checks_value = verification.get("checks") if isinstance(verification, dict) else None
    checks = checks_value if isinstance(checks_value, list) else []
    for check in checks:
        if isinstance(check, dict) and check.get("passed") is not True:
            failures.append(f"check_{check.get('name', 'unknown')}")
    return failures


def _build_simulation_payload(runtime: str, idea: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    workflow = _build_reproducibility(runtime, idea).get("workflow") or []
    return {
        "schema": LONG_HORIZON_SIMULATION_SCHEMA,
        "runtime": runtime,
        "workflow_path": list(workflow),
        "workflow_depth": len(list(workflow)),
        "replayable": True,
        "phase_status": ["planned" for _ in workflow],
        "provider_execution": _normalize_provider_execution(idea),
    }


def _normalize_provider_execution(idea: dict[str, Any]) -> dict[str, Any]:
    raw = idea.get("provider_execution")
    if isinstance(raw, dict):
        return dict(raw)

    provider = str(idea.get("provider", "")).strip()
    host_mode = str(idea.get("host_mode", "")).strip()
    smoke_status = str(idea.get("smoke_status", "")).strip()
    if not any((provider, host_mode, smoke_status)):
        return {}
    return {
        "provider": provider,
        "host_mode": host_mode,
        "smoke_status": smoke_status,
    }


def _build_provenance(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    provider_execution = _normalize_provider_execution(idea)
    host_mode = str(provider_execution.get("host_mode") or idea.get("host_mode") or f"{runtime}_native")
    return {
        "runtime": runtime,
        "host_mode": host_mode,
        "provider_execution": provider_execution,
        "goal": str(idea.get("goal", "")).strip(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_reproducibility(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    provider_execution = _normalize_provider_execution(idea)
    command = f"omg runtime dispatch --runtime {runtime}"
    if provider_execution.get("provider"):
        command += f" --provider {provider_execution['provider']}"
    if provider_execution.get("host_mode"):
        command += f" --host-mode {provider_execution['host_mode']}"
    if provider_execution.get("smoke_status"):
        command += f" --smoke-status {provider_execution['smoke_status']}"
    goal = str(idea.get("goal", "")).strip() or "unspecified-goal"
    return {
        "command": command,
        "resume_supported": True,
        "resume_key": f"{runtime}:{goal}".replace(" ", "-").lower(),
        "workflow": idea.get("workflow") or idea.get("workflow_path") or [],
    }


def _normalize_evidence(runtime: str, idea: dict[str, Any], verification: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    payload = dict(evidence) if isinstance(evidence, dict) else {}
    failure_taxonomy = _build_failure_taxonomy(idea, verification)
    payload["schema"] = EVIDENCE_PACK_SCHEMA
    payload.setdefault("runtime", runtime)
    payload.setdefault("phase", "evidence")
    payload.setdefault("status", "collected")
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("tests", verification.get("checks", []) if isinstance(verification, dict) else [])
    payload.setdefault("security_scans", [])
    payload.setdefault("diff_summary", {})
    payload["provider_execution"] = _normalize_provider_execution(idea)
    reproducibility = payload.get("reproducibility")
    if not isinstance(reproducibility, dict):
        reproducibility = {}
    reproducibility.setdefault("command", _build_reproducibility(runtime, idea)["command"])
    reproducibility.setdefault("resume_supported", True)
    payload["reproducibility"] = reproducibility
    payload["simulation"] = _build_simulation_payload(runtime, idea, verification)
    payload["failure_taxonomy"] = failure_taxonomy
    payload.setdefault("unresolved_risks", [])
    return payload


def _build_error_result(runtime: str, idea: dict[str, Any], error_code: str, message: str, *, retryable: bool) -> dict[str, Any]:
    category = "runtime_not_found" if error_code == "RUNTIME_NOT_FOUND" else "runtime_execution_failed"
    return {
        "schema": RUNTIME_DISPATCH_SCHEMA,
        "status": "error",
        "error_code": error_code,
        "runtime": runtime,
        "message": message,
        "failure": {
            "category": category,
            "retryable": retryable,
            "message": message,
        },
        "provenance": _build_provenance(runtime, idea),
        "reproducibility": _build_reproducibility(runtime, idea),
    }


def dispatch_runtime(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    adapters = get_adapters()
    adapter = adapters.get(runtime)
    if adapter is None:
        return _build_error_result(
            runtime,
            idea,
            "RUNTIME_NOT_FOUND",
            f"Unknown runtime: {runtime}",
            retryable=False,
        )

    try:
        plan = adapter.plan(idea)
        execution = adapter.execute(plan)
        verification = adapter.verify(execution)
        evidence = _normalize_evidence(runtime, idea, verification, adapter.collect_evidence(verification))
        business_workflow = build_business_workflow_result(
            idea=idea,
            plan=plan,
            execution=execution,
            verification=verification,
        )
        return {
            "schema": RUNTIME_DISPATCH_SCHEMA,
            "status": "ok",
            "runtime": runtime,
            "plan": plan,
            "execution": execution,
            "verification": verification,
            "evidence": evidence,
            "verification_status": dict(business_workflow.get("verification_summary", {})),
            "provenance": _build_provenance(runtime, idea),
            "reproducibility": _build_reproducibility(runtime, idea),
            "business_workflow": business_workflow,
        }
    except Exception as exc:  # pragma: no cover - defensive guard
        return _build_error_result(
            runtime,
            idea,
            "RUNTIME_EXECUTION_FAILED",
            str(exc),
            retryable=True,
        )
