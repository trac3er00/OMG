"""Tests for runtime dispatch orchestration."""

from runtime.dispatcher import dispatch_runtime


def test_dispatch_runtime_ok():
    result = dispatch_runtime("claude", {"goal": "ship feature"})
    assert result["schema"] == "OmgRuntimeDispatch"
    assert result["status"] == "ok"
    assert result["runtime"] == "claude"
    assert "plan" in result
    assert "execution" in result
    assert "verification" in result
    assert "evidence" in result
    assert result["evidence"]["schema"] == "OmgEvidencePack"
    assert result["verification_status"]["state"] == "verified"
    assert result["provenance"]["runtime"] == "claude"
    assert "business_workflow" in result
    workflow = result["business_workflow"]
    assert workflow["workflow_path"] == [
        "plan",
        "implement",
        "qa",
        "simulate",
        "final_test",
        "production",
    ]


def test_dispatch_runtime_not_found():
    result = dispatch_runtime("does-not-exist", {"goal": "x"})
    assert result["schema"] == "OmgRuntimeDispatch"
    assert result["status"] == "error"
    assert result["error_code"] == "RUNTIME_NOT_FOUND"
    assert result["failure"]["category"] == "runtime_not_found"


def test_dispatch_runtime_respects_user_workflow_path_and_instructions():
    idea = {
        "goal": "deliver release",
        "workflow": ["plan", "qa", "simulate"],
        "user_instructions": ["prioritize checkout stability", "keep deployment under 30 minutes"],
        "constraints": ["no schema migration"],
        "acceptance": ["all smoke tests pass"],
    }
    result = dispatch_runtime("local", idea)
    assert result["status"] == "ok"

    workflow = result["business_workflow"]
    assert workflow["requested_workflow_path"] == ["plan", "qa", "simulate"]
    assert workflow["workflow_path"] == [
        "plan",
        "qa",
        "simulate",
        "implement",
        "final_test",
        "production",
    ]
    assert workflow["task_plan"]["task_count"] >= 5
    assert workflow["verification_summary"]["state"] == "verified"
    assert result["evidence"]["simulation"]["schema"] == "OmgLongHorizonSimulation"
    assert result["business_workflow"]["qualification"]["schema"] == "OmgModelFactoryQualification"
