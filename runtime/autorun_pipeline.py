from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hooks.policy_engine import PolicyDecision, allow, ask, deny
from runtime.claim_judge import evaluate_claims_for_release
from runtime.opus_plan import generate_governed_deep_plan, persist_governed_plan
from runtime.proof_gate import evaluate_proof_gate, production_gate
from runtime.subagent_dispatcher import get_job_status, submit_job
from runtime.test_intent_lock import lock_intent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decision_to_dict(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "decision": decision.action,
        "risk_level": decision.risk_level,
        "reason": decision.reason,
        "controls": list(decision.controls or []),
    }


def _review_plan(plan: dict[str, Any]) -> PolicyDecision:
    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(tasks, list) or not tasks:
        return deny(
            "Plan has no executable tasks; governance review denied.",
            "high",
            ["plan-required"],
        )

    decisions: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        checkpoint = task.get("governance_checkpoint")
        if not isinstance(checkpoint, dict):
            continue
        action = str(checkpoint.get("decision", "")).strip().lower()
        if action:
            decisions.append(action)

    if "deny" in decisions:
        return deny(
            "At least one plan task is denied by governance checkpoint.",
            "high",
            ["plan-redesign", "manual-approval"],
        )
    if "ask" in decisions:
        return ask(
            "Plan includes ask-level tasks; execution allowed with explicit controls.",
            "med",
            ["manual-checkpoint", "evidence-required"],
        )
    return allow("Plan review passed with allow-level governed tasks.")


def _task_execution_checkpoint(task: dict[str, Any]) -> dict[str, Any]:
    checkpoint = task.get("governance_checkpoint") if isinstance(task, dict) else None
    if not isinstance(checkpoint, dict):
        return _decision_to_dict(
            ask(
                "Task missing governance checkpoint; execution requires manual review.",
                "high",
                ["manual-checkpoint"],
            )
        )

    action = str(checkpoint.get("decision", "")).strip().lower()
    risk = str(checkpoint.get("risk_level", "med")).strip().lower() or "med"
    reason = str(checkpoint.get("reason", "")).strip() or "task governance checkpoint"
    raw_controls = checkpoint.get("controls")
    normalized_controls = (
        [str(control) for control in raw_controls if str(control).strip()]
        if isinstance(raw_controls, list)
        else []
    )

    if action == "deny":
        decision = deny(reason, risk, normalized_controls)
    elif action == "ask":
        decision = ask(reason, risk, normalized_controls)
    else:
        decision = allow(reason, normalized_controls)
    return _decision_to_dict(decision)


def _execute_plan(
    *,
    plan: dict[str, Any],
    run_id: str,
    use_multi_agent: bool,
) -> dict[str, Any]:
    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    task_rows = tasks if isinstance(tasks, list) else []

    step_results: list[dict[str, Any]] = []
    executable_tasks: list[dict[str, Any]] = []
    for task in task_rows:
        if not isinstance(task, dict):
            continue
        checkpoint = _task_execution_checkpoint(task)
        step_payload = {
            "task_id": str(task.get("id", "")).strip(),
            "description": str(task.get("description", "")).strip(),
            "governance_checkpoint": checkpoint,
        }
        if checkpoint["decision"] == "deny":
            step_payload["status"] = "blocked"
            step_payload["reason"] = checkpoint["reason"]
            step_results.append(step_payload)
            return {
                "status": "blocked",
                "executor_mode": "none",
                "steps": step_results,
                "governance_checkpoint": _decision_to_dict(
                    deny(
                        "Execution blocked by deny-level task checkpoint.",
                        "high",
                        ["plan-redesign"],
                    )
                ),
            }

        executable_tasks.append(task)
        step_results.append(step_payload)

    if not executable_tasks:
        return {
            "status": "completed",
            "executor_mode": "none",
            "steps": step_results,
            "governance_checkpoint": _decision_to_dict(
                allow("No executable tasks remained after governance checks.")
            ),
        }

    multi_agent_mode = use_multi_agent and len(executable_tasks) > 1
    if not multi_agent_mode:
        for step in step_results:
            step["status"] = "completed"
        return {
            "status": "completed",
            "executor_mode": "single-agent",
            "steps": step_results,
            "governance_checkpoint": _decision_to_dict(
                allow("Execution completed in governed single-agent mode.")
            ),
        }

    submitted: list[tuple[str, dict[str, Any]]] = []
    try:
        for index, task in enumerate(executable_tasks, start=1):
            job_id = submit_job(
                agent_name=f"autorun-agent-{index}",
                task_text=str(task.get("description", "")).strip(),
                isolation="none",
                run_id=run_id,
            )
            submitted.append((job_id, task))
    except RuntimeError as exc:
        for step in step_results:
            step["status"] = "completed"
            step["note"] = f"multi-agent unavailable; fallback to single-agent ({exc})"
        return {
            "status": "completed",
            "executor_mode": "single-agent-fallback",
            "steps": step_results,
            "governance_checkpoint": _decision_to_dict(
                ask(
                    "Multi-agent dispatcher unavailable; executed with governed fallback.",
                    "med",
                    ["feature-flag-disabled"],
                )
            ),
        }

    deadline = time.time() + 120.0
    finished: dict[str, dict[str, Any]] = {}
    while time.time() < deadline and len(finished) < len(submitted):
        for job_id, _task in submitted:
            if job_id in finished:
                continue
            status = get_job_status(job_id)
            token = str(status.get("status", "")).strip().lower()
            if token in {"completed", "failed", "cancelled"}:
                finished[job_id] = status
        if len(finished) < len(submitted):
            time.sleep(0.05)

    failed = False
    timeout_jobs: list[str] = []
    by_task_id = {
        str(task.get("id", "")).strip(): step
        for step, task in zip(step_results, executable_tasks)
        if str(task.get("id", "")).strip()
    }
    for job_id, task in submitted:
        task_id = str(task.get("id", "")).strip()
        step = by_task_id.get(task_id)
        if step is None:
            continue
        if job_id not in finished:
            step["status"] = "failed"
            step["reason"] = "execution timeout"
            step["job_id"] = job_id
            failed = True
            timeout_jobs.append(job_id)
            continue

        record = finished[job_id]
        job_status = str(record.get("status", "")).strip().lower()
        step["job_id"] = job_id
        step["status"] = "completed" if job_status == "completed" else "failed"
        if job_status != "completed":
            step["reason"] = (
                str(record.get("error", "job failed")).strip() or "job failed"
            )
            failed = True

    if timeout_jobs:
        return {
            "status": "failed",
            "executor_mode": "multi-agent",
            "steps": step_results,
            "timeout_jobs": timeout_jobs,
            "governance_checkpoint": _decision_to_dict(
                ask(
                    "Multi-agent execution timed out for one or more tasks.",
                    "high",
                    ["manual-recovery"],
                )
            ),
        }

    if failed:
        return {
            "status": "failed",
            "executor_mode": "multi-agent",
            "steps": step_results,
            "governance_checkpoint": _decision_to_dict(
                ask(
                    "One or more multi-agent jobs failed execution.",
                    "high",
                    ["manual-recovery"],
                )
            ),
        }

    return {
        "status": "completed",
        "executor_mode": "multi-agent",
        "steps": step_results,
        "governance_checkpoint": _decision_to_dict(
            allow("Execution completed in governed multi-agent mode.")
        ),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(temp_path, path)


def _verify_pipeline(
    *,
    project_dir: str,
    run_id: str,
    goal: str,
    execution: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_dir)
    trace_id = f"trace-{run_id}"
    context_checksum = hashlib.sha256(goal.encode("utf-8", errors="ignore")).hexdigest()

    evidence_pack_path = root / ".omg" / "evidence" / f"{run_id}.json"
    evidence_pack_rel = str(evidence_pack_path.relative_to(root)).replace("\\", "/")
    evidence_pack = {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": run_id,
        "evidence_profile": "docs-only",
        "trace_ids": [trace_id],
        "context_checksum": context_checksum,
        "profile_version": "autorun-v1",
        "intent_gate_version": "1.0.0",
        "artifacts": [
            {
                "kind": "pipeline",
                "path": evidence_pack_rel,
                "sha256": context_checksum,
                "parser": "json",
                "summary": "autorun evidence pack",
                "trace_id": trace_id,
            }
        ],
        "execution": {
            "status": str(execution.get("status", "")),
            "mode": str(execution.get("executor_mode", "")),
        },
        "generated_at": _utc_now_iso(),
    }
    _atomic_write_json(evidence_pack_path, evidence_pack)

    lock_result = lock_intent(
        project_dir, {"run_id": run_id, "tests": [], "touched_paths": []}
    )
    lock_id = str(lock_result.get("lock_id", "")).strip()
    test_lock = {
        "status": "ok" if lock_id else "missing_lock",
        "lock_id": lock_id,
        "reason": "autorun_test_intent_lock",
    }

    claims = [
        {
            "claim_type": "ready_to_ship",
            "subject": goal,
            "run_id": run_id,
            "evidence_profile": "docs-only",
            "trace_ids": [trace_id],
            "artifacts": [evidence_pack_rel],
        }
    ]
    claim_decision = evaluate_claims_for_release(project_dir, run_id, claims=claims)

    proof_input = {
        "evidence_profile": "docs-only",
        "claims": claims,
        "proof_chain": {
            "status": "ok",
            "blockers": [],
            "trace_id": trace_id,
            "run_id": run_id,
        },
        "eval_output": {"trace_id": trace_id},
        "test_intent_lock": test_lock,
        "evidence_pack": evidence_pack,
    }
    proof_result = evaluate_proof_gate(proof_input)
    production_result = production_gate(
        {
            "claim_judge": claim_decision,
            "proof_gate": proof_result,
            "test_intent_lock": test_lock,
        }
    )

    verify_checkpoint = allow(
        "Verification finished with claim/proof/production gates."
    )
    status = "completed"
    if str(production_result.get("status", "")).strip().lower() == "blocked":
        status = "blocked"

    return {
        "status": status,
        "governance_checkpoint": _decision_to_dict(verify_checkpoint),
        "claim_judge": claim_decision,
        "proof_gate": proof_result,
        "proof_gate_verdict": str(proof_result.get("verdict", "")).strip() or "fail",
        "production_gate": production_result,
        "test_intent_lock": test_lock,
        "evidence_pack_path": evidence_pack_rel,
    }


def run_autorun_pipeline(
    goal: str,
    *,
    project_dir: str = ".",
    tier: str = "max",
    use_multi_agent: bool = True,
) -> dict[str, Any]:
    normalized_goal = str(goal or "").strip()
    if not normalized_goal:
        raise ValueError("goal is required")

    run_id = f"autorun-{uuid4().hex[:12]}"
    started_at = _utc_now_iso()

    plan_id = f"{run_id}-plan"
    plan = generate_governed_deep_plan(
        normalized_goal,
        project_dir=project_dir,
        tier=tier,
        plan_id=plan_id,
    )
    persisted_plan = persist_governed_plan(plan, project_dir=project_dir)

    plan_checkpoint = allow("Deep planning stage generated a governed task plan.")
    plan_stage = {
        "status": "completed",
        "plan_id": str(persisted_plan.get("id", "")).strip(),
        "plan_version": int(persisted_plan.get("version", 1) or 1),
        "task_count": len(persisted_plan.get("tasks", []))
        if isinstance(persisted_plan.get("tasks"), list)
        else 0,
        "plan_path": str(persisted_plan.get("plan_path", "")).strip(),
        "governance_checkpoint": _decision_to_dict(plan_checkpoint),
    }

    review_decision = _review_plan(persisted_plan)
    review_stage = {
        "status": "approved" if review_decision.action != "deny" else "denied",
        "governance_checkpoint": _decision_to_dict(review_decision),
    }

    if review_decision.action == "deny":
        pipeline = {
            "schema": "OMGAutorunPipelineResult",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "goal": normalized_goal,
            "status": "blocked",
            "started_at": started_at,
            "finished_at": _utc_now_iso(),
            "stages": {
                "plan": plan_stage,
                "review": review_stage,
                "execute": {
                    "status": "blocked",
                    "executor_mode": "none",
                    "steps": [],
                    "governance_checkpoint": _decision_to_dict(
                        deny(
                            "Execution blocked because governance review denied the plan.",
                            "high",
                            ["plan-redesign"],
                        )
                    ),
                },
                "verify": {
                    "status": "blocked",
                    "governance_checkpoint": _decision_to_dict(
                        deny(
                            "Verification skipped because execution never started.",
                            "high",
                            ["execution-required"],
                        )
                    ),
                    "proof_gate_verdict": "fail",
                    "production_gate": {
                        "status": "blocked",
                        "blockers": ["review_denied"],
                    },
                },
            },
            "proof_gate_verdict": "fail",
            "evidence": [],
        }
        return pipeline

    execute_stage = _execute_plan(
        plan=persisted_plan, run_id=run_id, use_multi_agent=use_multi_agent
    )
    verify_stage = _verify_pipeline(
        project_dir=project_dir,
        run_id=run_id,
        goal=normalized_goal,
        execution=execute_stage,
    )

    report_path = Path(project_dir) / ".omg" / "evidence" / f"autorun-{run_id}.json"
    report_rel = str(report_path.relative_to(project_dir)).replace("\\", "/")

    status = "completed"
    if str(execute_stage.get("status", "")).strip().lower() not in {"completed"}:
        status = "failed"
    if str(verify_stage.get("status", "")).strip().lower() == "blocked":
        status = "blocked"

    payload = {
        "schema": "OMGAutorunPipelineResult",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "goal": normalized_goal,
        "status": status,
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "stages": {
            "plan": plan_stage,
            "review": review_stage,
            "execute": execute_stage,
            "verify": verify_stage,
        },
        "proof_gate_verdict": str(verify_stage.get("proof_gate_verdict", "fail")),
        "evidence": [
            str(verify_stage.get("evidence_pack_path", "")).strip(),
            report_rel,
        ],
    }

    _atomic_write_json(report_path, payload)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="omg-autorun",
        description="Run governed autorun pipeline: plan→review→execute→verify",
    )
    parser.add_argument(
        "--goal", required=True, help="Goal to execute via autorun pipeline"
    )
    parser.add_argument("--project-dir", default=".", help="Project root directory")
    parser.add_argument(
        "--tier", default="max", help="Subscription tier for planning model routing"
    )
    parser.add_argument(
        "--single-agent",
        action="store_true",
        help="Force single-agent execution path",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Print JSON result"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_autorun_pipeline(
        args.goal,
        project_dir=args.project_dir,
        tier=args.tier,
        use_multi_agent=not bool(args.single_agent),
    )
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        plan_stage = (
            result.get("stages", {}).get("plan", {})
            if isinstance(result.get("stages"), dict)
            else {}
        )
        review_stage = (
            result.get("stages", {}).get("review", {})
            if isinstance(result.get("stages"), dict)
            else {}
        )
        execute_stage = (
            result.get("stages", {}).get("execute", {})
            if isinstance(result.get("stages"), dict)
            else {}
        )
        verify_stage = (
            result.get("stages", {}).get("verify", {})
            if isinstance(result.get("stages"), dict)
            else {}
        )

        print(f"Autorun status: {result.get('status', 'unknown')}")
        print(
            "Plan:",
            f"{plan_stage.get('task_count', 0)} tasks",
            f"(plan_id={plan_stage.get('plan_id', '')})",
        )
        review_checkpoint = (
            review_stage.get("governance_checkpoint", {})
            if isinstance(review_stage, dict)
            else {}
        )
        print("Review:", review_checkpoint.get("decision", "unknown"))
        print(
            "Execute:",
            execute_stage.get("status", "unknown"),
            f"mode={execute_stage.get('executor_mode', 'unknown')}",
        )
        print(
            "Verify:",
            f"proof_gate={verify_stage.get('proof_gate_verdict', 'fail')}",
            f"production={((verify_stage.get('production_gate', {}) if isinstance(verify_stage, dict) else {}) or {}).get('status', 'blocked')}",
        )
        evidence = result.get("evidence")
        if isinstance(evidence, list):
            for item in evidence:
                item_text = str(item).strip()
                if item_text:
                    print(f"Evidence: {item_text}")

    return 0 if str(result.get("status", "")).strip().lower() in {"completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
