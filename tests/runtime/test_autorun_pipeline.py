from __future__ import annotations

from pathlib import Path

from runtime.autorun_pipeline import run_autorun_pipeline


def test_autorun_pipeline_stages(tmp_path: Path) -> None:
    result = run_autorun_pipeline(
        "create a REST API endpoint",
        project_dir=tmp_path.as_posix(),
        use_multi_agent=False,
    )

    assert result["schema"] == "OMGAutorunPipelineResult"
    assert "stages" in result
    stages = result["stages"]
    assert stages["plan"]["status"] == "completed"
    assert stages["review"]["status"] in {"approved", "denied"}
    assert stages["execute"]["status"] in {"completed", "failed", "blocked"}
    assert stages["verify"]["status"] in {"completed", "blocked"}


def test_autorun_governance_at_each_stage(tmp_path: Path) -> None:
    result = run_autorun_pipeline(
        "create a REST API endpoint",
        project_dir=tmp_path.as_posix(),
        use_multi_agent=False,
    )
    stages = result["stages"]

    for stage_name in ("plan", "review", "execute", "verify"):
        checkpoint = stages[stage_name].get("governance_checkpoint")
        assert isinstance(checkpoint, dict), f"missing checkpoint for {stage_name}"
        assert checkpoint.get("decision") in {"allow", "ask", "deny"}

    per_step = stages["execute"].get("steps", [])
    assert isinstance(per_step, list)
    assert per_step
    for step in per_step:
        checkpoint = step.get("governance_checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("decision") in {"allow", "ask", "deny"}


def test_autorun_proof_gate_verdict(tmp_path: Path) -> None:
    result = run_autorun_pipeline(
        "create a REST API endpoint",
        project_dir=tmp_path.as_posix(),
        use_multi_agent=False,
    )

    verify = result["stages"]["verify"]
    proof_gate = verify.get("proof_gate")
    assert isinstance(proof_gate, dict)
    assert proof_gate.get("verdict") in {"pass", "fail"}
    assert result.get("proof_gate_verdict") in {"pass", "fail"}
    assert result.get("proof_gate_verdict") == verify.get("proof_gate_verdict")
