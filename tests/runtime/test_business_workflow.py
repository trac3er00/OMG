from runtime.business_workflow import build_business_workflow_result


def test_business_workflow_blocks_production_when_checks_missing():
    workflow = build_business_workflow_result(
        idea={"goal": "release"},
        plan={"status": "planned"},
        execution={"status": "executed"},
        verification={},
    )
    assert workflow["ready_for_production"] is False
    statuses = {entry["stage"]: entry["status"] for entry in workflow["stage_status"]}
    assert statuses["qa"] == "failed"
    assert statuses["simulate"] == "failed"
    assert statuses["final_test"] == "failed"
    assert statuses["production"] == "blocked"


def test_business_workflow_ready_only_when_all_checks_pass():
    workflow = build_business_workflow_result(
        idea={"goal": "release"},
        plan={"status": "planned"},
        execution={"status": "executed"},
        verification={"checks": [{"name": "tests", "passed": True}, {"name": "security", "passed": True}]},
    )
    assert workflow["ready_for_production"] is True
    statuses = {entry["stage"]: entry["status"] for entry in workflow["stage_status"]}
    assert statuses["qa"] == "completed"
    assert statuses["simulate"] == "completed"
    assert statuses["final_test"] == "completed"
    assert statuses["production"] == "ready"


def test_business_workflow_marks_provider_degradation_and_evidence_requirements():
    workflow = build_business_workflow_result(
        idea={
            "goal": "release",
            "provider_execution": {
                "provider": "codex",
                "host_mode": "claude_dispatch",
                "smoke_status": "mcp_unreachable",
            },
            "evidence_required": {
                "tests": ["pytest -q"],
                "security_scans": ["bandit -r src"],
                "reproducibility": ["seed=deterministic"],
                "artifacts": ["report.json"],
            },
        },
        plan={"status": "planned"},
        execution={"status": "executed"},
        verification={"checks": [{"name": "tests", "passed": True}, {"name": "security", "passed": True}]},
    )
    statuses = {entry["stage"]: entry["status"] for entry in workflow["stage_status"]}
    assert workflow["verification_summary"]["state"] == "degraded"
    assert statuses["qa"] == "degraded"
    assert statuses["production"] == "blocked"
    assert workflow["provider_execution"]["smoke_status"] == "mcp_unreachable"
    assert workflow["evidence_requirements"]["tests"] == ["pytest -q"]


def test_business_workflow_emits_model_factory_qualification_summary():
    workflow = build_business_workflow_result(
        idea={
            "goal": "factory",
            "workflow": ["plan", "implement", "qa", "simulate", "final_test", "production"],
        },
        plan={"status": "planned"},
        execution={"status": "executed"},
        verification={"checks": [{"name": "tests", "passed": True}]},
    )

    qualification = workflow["qualification"]
    assert qualification["schema"] == "OmgModelFactoryQualification"
    assert qualification["workflow_depth"] >= 6
    assert qualification["long_horizon_ready"] is True
    assert qualification["failure_taxonomy"] == []
