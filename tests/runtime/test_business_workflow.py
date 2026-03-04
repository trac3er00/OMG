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
