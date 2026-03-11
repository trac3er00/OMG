from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.subagent_dispatcher import resolve_execution_boundary
from runtime.untrusted_content import write_sandbox_budget_evidence
from tools.python_sandbox import execute_budgeted_run


@dataclass(frozen=True)
class ForgeRunSpec:
    run_id: str
    adapter: str
    budget: dict[str, Any]
    outbound_allowlist: list[str]
    trainer_code: str = "print('forge trainer ready')"
    sidecar_code: str | None = None
    attempted_outbound: list[str] | None = None
    project_dir: str = "."


@dataclass(frozen=True)
class ForgeRunResult:
    status: str
    evidence: dict[str, Any]
    checkpoint_paths: list[str]


def run_forge_sandboxed(spec: ForgeRunSpec) -> ForgeRunResult:
    budget_time = int(spec.budget.get("time_seconds", 0) or 0)
    budget_cost = float(spec.budget.get("cost_usd", 0.0) or 0.0)
    gpu_allowed = bool(spec.budget.get("gpu_allowed", False))

    execution = execute_budgeted_run(
        trainer_code=spec.trainer_code,
        sidecar_code=spec.sidecar_code,
        time_budget_seconds=max(1, budget_time),
        cost_budget_usd=max(0.0, budget_cost),
        gpu_allowed=gpu_allowed,
        outbound_allowlist=spec.outbound_allowlist,
        attempted_outbound=spec.attempted_outbound,
    )

    outbound_blocked_count = int(execution.get("outbound_blocked_count", 0))
    isolation: dict[str, Any] = {
        **resolve_execution_boundary(isolation="worktree"),
        "sandbox_mode": str(execution.get("sandbox_mode", "isolated-subprocess")),
        "outbound_blocked_count": outbound_blocked_count,
        "process_count": int(execution.get("process_count", 1)),
    }
    budget_evidence = {
        "time_used_seconds": float(execution.get("time_used_seconds", 0.0)),
        "time_budget_seconds": max(1, budget_time),
        "cost_estimate_usd": float(execution.get("estimated_cost_usd", 0.0)),
        "cost_budget_usd": max(0.0, budget_cost),
        "network_calls_attempted": int(execution.get("network_calls_attempted", 0)),
        "network_calls_allowed": int(execution.get("network_calls_allowed", 0)),
        "blocked_targets": list(execution.get("blocked_targets", [])),
    }

    status = str(execution.get("status", "error"))
    reason = str(execution.get("error") or "")
    if outbound_blocked_count > 0:
        status = "blocked"
        reason = reason or "outbound target blocked by allowlist"
    if bool(execution.get("requested_gpu", False)) and not gpu_allowed:
        status = "blocked"
        reason = "gpu requested by workload but disallowed by budget"

    isolation_payload: dict[str, Any] = {
        **isolation,
        "reason": reason,
    }
    evidence: dict[str, Any] = {
        "run_id": spec.run_id,
        "adapter": spec.adapter,
        "status": status,
        "reason": reason,
        "budget": budget_evidence,
        "isolation": isolation_payload,
    }

    trust_path = write_sandbox_budget_evidence(
        project_dir=spec.project_dir,
        run_id=spec.run_id,
        budget=budget_evidence,
        isolation=isolation_payload,
    )
    evidence["trust_evidence_path"] = trust_path

    checkpoints = [str(path) for path in execution.get("checkpoint_paths", [])]
    if checkpoints:
        run_dir = Path(spec.project_dir) / ".omg" / "evidence" / "forge"
        run_dir.mkdir(parents=True, exist_ok=True)
        evidence["checkpoint_dir"] = str(run_dir)

    return ForgeRunResult(
        status=status,
        evidence=evidence,
        checkpoint_paths=checkpoints,
    )
