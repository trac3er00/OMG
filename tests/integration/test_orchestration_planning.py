# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportInvalidTypeForm=false, reportReturnType=false, reportAny=false, reportUnknownArgumentType=false, reportUnusedFunction=false, reportUnusedCallResult=false, reportPrivateLocalImportUsage=false, reportExplicitAny=false, reportUnknownLambdaType=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.budget_envelopes import BudgetEnvelopeManager
from runtime.opus_plan import generate_governed_deep_plan, persist_governed_plan
from runtime.proof_gate import evaluate_proof_gate, production_gate
from runtime.router_selector import select_target
from runtime.skill_evolution import evaluate_proposal, promote_if_proven, propose_skill
from runtime.subagent_dispatcher import (
    _agent_coordinator,
    _jobs,
    _lock,
    get_job_status,
    shutdown,
    submit_job,
)
from runtime.tool_plan_gate import build_tool_plan, tool_plan_gate_check


class _ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        return fn(*args, **kwargs)


def _model_tiers() -> dict[str, dict[str, str]]:
    return {
        "claude": {
            "light": "claude-light",
            "balanced": "claude-balanced",
            "heavy": "claude-heavy",
        },
        "gpt-5.4": {
            "light": "gpt-light",
            "balanced": "gpt-balanced",
            "heavy": "gpt-heavy",
        },
        "kimi": {
            "light": "kimi-light",
            "balanced": "kimi-balanced",
            "heavy": "kimi-heavy",
        },
    }


@pytest.fixture(autouse=True)
def _reset_subagent_state() -> None:
    with _lock:
        _jobs.clear()
    _agent_coordinator.clear()
    yield
    with _lock:
        _jobs.clear()
    _agent_coordinator.clear()
    shutdown(wait=False)


def test_planning_governance_execution_and_proof_gate_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_PARALLEL_SUBAGENTS_ENABLED", "1")
    monkeypatch.setenv("OMG_SUBAGENT_RUNNER", "stub")
    monkeypatch.setenv("OMG_SUBAGENT_STUB_OUTPUT", "governed execution complete")

    import runtime.subagent_dispatcher as subagent_dispatcher

    monkeypatch.setattr(
        subagent_dispatcher, "get_executor", lambda: _ImmediateExecutor()
    )

    plan = generate_governed_deep_plan(
        objective="Implement governed orchestration pipeline",
        tasks=[
            "Analyze orchestration objective and constraints",
            "Edit workflow and validate evidence chain",
            "Review proof-gate readiness and publish report",
        ],
        tier="pro",
        project_dir=str(tmp_path),
        plan_id="plan-orchestration-e2e",
    )
    persisted = persist_governed_plan(plan, project_dir=str(tmp_path))

    assert persisted["id"] == "plan-orchestration-e2e"
    tasks = persisted["tasks"]
    assert tasks
    assert all(isinstance(task.get("governance_checkpoint"), dict) for task in tasks)

    job_id = submit_job(
        "planner-agent",
        "Execute governed plan with proof artifacts",
        run_id="plan-orchestration-e2e",
    )
    job_status = get_job_status(job_id)
    assert job_status["status"] == "completed"
    artifacts = job_status.get("artifacts", [])
    assert artifacts
    evidence_rel = str(artifacts[0]["evidence_path"])
    assert (tmp_path / evidence_rel).exists()

    proof_result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "orchestration_ready",
                    "artifacts": [
                        "junit.xml",
                        "coverage.xml",
                        "scan.sarif",
                        "trace.zip",
                    ],
                    "trace_ids": ["trace-orch-e2e"],
                }
            ],
            "proof_chain": {
                "status": "ok",
                "blockers": [],
                "trace_id": "trace-orch-e2e",
            },
            "eval_output": {"trace_id": "trace-orch-e2e", "status": "ok"},
        }
    )
    assert proof_result["verdict"] == "pass"

    production_result = production_gate(
        {
            "claim_judge": {"status": "ok", "claim_judge_verdict": "pass"},
            "proof_gate": proof_result,
            "test_intent_lock": {"status": "ok", "lock_id": "lock-orch-e2e"},
        }
    )
    assert production_result["status"] == "ok"


def test_multi_model_routing_budget_tracking_and_plan_adherence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_MULTI_MODEL_ROUTING_ENABLED", "1")

    routing = select_target(
        (
            "Design a full-stack orchestration migration with rollout phases, "
            "cross-service dependency analysis, rollback constraints, and "
            "end-to-end verification gates"
        ),
        "governance-heavy planning",
        budget_remaining_ratio=0.1,
        model_tiers=_model_tiers(),
    )
    assert routing["model_tier"] in {"light", "balanced"}
    assert routing["model_tier"] != "heavy"
    assert routing["budget_remaining_ratio"] == 0.1
    assert "budget<20%" in str(routing["reason"])

    manager = BudgetEnvelopeManager(str(tmp_path))
    manager.create_envelope(
        "run-orch-budget", token_limit=20, wall_time_seconds_limit=2
    )
    manager.record_usage("run-orch-budget", tokens=24, wall_time_seconds=3)
    check = manager.check_envelope("run-orch-budget")
    assert check.status == "breach"
    assert check.governance_action == "block"

    _ = build_tool_plan(
        "need docs and security audit",
        available_tools=["context7", "omg_security_check"],
        run_id="run-orch-budget",
    )

    blocked = tool_plan_gate_check(
        str(tmp_path),
        "run-orch-budget",
        "Write",
        tool_input={"metadata": {"done_when": ["orchestration tests pass"]}},
    )
    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "test_intent_lock_required_before_mutation"

    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock-orch-budget.json").write_text(
        json.dumps(
            {"lock_id": "lock-orch-budget", "intent": {"run_id": "run-orch-budget"}}
        ),
        encoding="utf-8",
    )

    allowed = tool_plan_gate_check(
        str(tmp_path),
        "run-orch-budget",
        "Write",
        tool_input={
            "lock_id": "lock-orch-budget",
            "metadata": {"done_when": ["orchestration tests pass"]},
        },
    )
    assert allowed["status"] == "allowed"


def test_multi_agent_coordination_detects_cross_agent_file_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_PARALLEL_SUBAGENTS_ENABLED", "1")
    monkeypatch.setenv("OMG_MULTI_AGENT_CONFLICT_POLICY", "deny")

    import runtime.subagent_dispatcher as subagent_dispatcher

    monkeypatch.setattr(
        subagent_dispatcher, "get_executor", lambda: _ImmediateExecutor()
    )

    def _conflicting_dispatch(_: dict[str, Any], *, project_dir: str) -> dict[str, Any]:
        del project_dir
        return {
            "status": "ok",
            "worker": "stub",
            "output": "mutated shared file",
            "exit_code": 0,
            "modified_files": ["src/shared/conflict.py"],
        }

    monkeypatch.setattr(
        subagent_dispatcher, "_dispatch_job_task", _conflicting_dispatch
    )

    first_job = submit_job(
        "agent-a", "Update shared orchestration file", run_id="run-conflict"
    )
    first_status = get_job_status(first_job)
    assert first_status["status"] == "completed"

    second_job = submit_job(
        "agent-b", "Update same shared orchestration file", run_id="run-conflict"
    )
    second_status = get_job_status(second_job)
    assert second_status["status"] == "failed"
    assert "cross-agent file ownership conflict detected" in str(second_status["error"])
    conflict_gate = second_status.get("conflict_gate", {})
    assert conflict_gate.get("status") == "fired"
    assert conflict_gate.get("decision") == "deny"


def test_deep_planning_assigns_governance_checkpoint_to_every_step(
    tmp_path: Path,
) -> None:
    plan = generate_governed_deep_plan(
        objective="Ship orchestration flow safely",
        tasks=[
            {
                "id": "discover",
                "description": "Analyze orchestration constraints",
                "dependencies": [],
            },
            {
                "id": "mutate",
                "description": "Edit orchestration workflow",
                "dependencies": ["discover"],
            },
            {
                "id": "prod",
                "description": "Deploy production release notes",
                "dependencies": ["mutate"],
            },
            {
                "id": "danger",
                "description": "Delete obsolete release branch",
                "dependencies": ["prod"],
            },
        ],
        tier="max",
        project_dir=str(tmp_path),
        plan_id="plan-governance-checkpoints",
    )

    checkpoints = {item["task_id"]: item for item in plan["governance_checkpoints"]}
    assert len(checkpoints) == 4
    assert len(plan["tasks"]) == 4
    assert all("governance_checkpoint" in task for task in plan["tasks"])

    assert checkpoints["discover"]["decision"] == "allow"
    assert checkpoints["mutate"]["decision"] == "ask"
    assert checkpoints["prod"]["decision"] == "ask"
    assert checkpoints["danger"]["decision"] == "deny"


def test_skill_improvements_and_tool_descriptions_work_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    proposal = propose_skill(
        name="omg/orchestration-skill-v2",
        source="integration-test",
        description="Improved orchestration proof synthesis",
        metadata={"area": "orchestration", "version": 2},
    )

    import runtime.skill_evolution as skill_evolution

    monkeypatch.setattr(
        skill_evolution.proof_gate,
        "evaluate_proof_gate",
        lambda _: {
            "schema": "ProofGateResult",
            "verdict": "pass",
            "blockers": [],
            "evidence_summary": {"claim_count": 1},
        },
    )

    evaluated = evaluate_proposal(
        str(proposal["proposal_id"]),
        test_results={"claims": [{"claim_type": "orchestration_skill_verified"}]},
    )
    promoted = promote_if_proven(str(proposal["proposal_id"]))

    assert evaluated["status"] == "evaluated"
    assert evaluated["promotable"] is True
    assert promoted["status"] == "promoted"

    plan = build_tool_plan(
        "Need docs reference plus security policy audit for orchestration update",
        available_tools=["context7", "omg_security_check", "websearch"],
        run_id="run-skill-tools",
    )
    tools = plan["tools"]
    assert isinstance(tools, list)
    assert tools

    selected = {str(item["name"]): item for item in tools}
    assert "context7" in selected
    assert "omg_security_check" in selected
    assert selected["context7"]["args"] == {"query": plan["goal"]}
    assert selected["omg_security_check"]["args"] == {
        "scope": ".",
        "include_live_enrichment": False,
    }
    for item in tools:
        assert "matched capability" in str(item["rationale"])
