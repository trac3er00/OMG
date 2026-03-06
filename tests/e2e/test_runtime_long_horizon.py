"""Long-horizon runtime simulation and qualification coverage."""
from __future__ import annotations

from runtime.dispatcher import dispatch_runtime


def test_dispatch_runtime_emits_long_horizon_simulation_artifacts():
    result = dispatch_runtime(
        "claude",
        {
            "goal": "qualify long horizon runtime",
            "workflow": ["plan", "implement", "qa", "simulate", "final_test", "production"],
            "provider_execution": {
                "provider": "kimi",
                "host_mode": "claude_dispatch",
                "smoke_status": "success",
            },
            "evidence_required": {
                "tests": ["pytest -q tests/runtime"],
                "security_scans": ["bandit -r runtime hooks"],
                "reproducibility": ["seed=deterministic"],
                "artifacts": ["qualification.json"],
            },
        },
    )

    assert result["status"] == "ok"
    assert result["evidence"]["simulation"]["schema"] == "OmgLongHorizonSimulation"
    assert result["evidence"]["simulation"]["replayable"] is True
    assert result["evidence"]["simulation"]["workflow_depth"] >= 6
    assert result["evidence"]["failure_taxonomy"] == []
    assert result["business_workflow"]["qualification"]["schema"] == "OmgModelFactoryQualification"
    assert result["business_workflow"]["qualification"]["long_horizon_ready"] is True
    assert result["business_workflow"]["qualification"]["replayable"] is True


def test_dispatch_runtime_carries_failure_taxonomy_for_degraded_provider():
    result = dispatch_runtime(
        "claude",
        {
            "goal": "qualify degraded runtime",
            "workflow": ["plan", "qa", "simulate"],
            "provider_execution": {
                "provider": "codex",
                "host_mode": "claude_dispatch",
                "smoke_status": "auth_required",
            },
        },
    )

    assert result["status"] == "ok"
    assert "provider_auth_required" in result["evidence"]["failure_taxonomy"]
    assert result["business_workflow"]["qualification"]["long_horizon_ready"] is False
    assert "provider_auth_required" in result["business_workflow"]["qualification"]["failure_taxonomy"]
