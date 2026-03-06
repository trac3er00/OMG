"""Readiness contracts for long-horizon model-development runtime loops."""
from __future__ import annotations

from runtime.dispatcher import dispatch_runtime


def test_runtime_dispatch_emits_readiness_schema_and_provenance():
    result = dispatch_runtime(
        "claude",
        {
            "goal": "build model factory runtime",
            "workflow": ["plan", "qa"],
            "provider_execution": {
                "provider": "kimi",
                "host_mode": "claude_dispatch",
                "smoke_status": "success",
            },
            "evidence_required": {
                "tests": ["pytest -q tests/runtime"],
                "security_scans": ["bandit -r hooks runtime"],
                "reproducibility": ["seed=deterministic"],
                "artifacts": ["readiness-report.json"],
            },
        },
    )

    assert result["schema"] == "OmgRuntimeDispatch"
    assert result["status"] == "ok"
    assert result["verification_status"]["state"] == "verified"
    assert result["provenance"]["provider_execution"]["provider"] == "kimi"
    assert result["provenance"]["host_mode"] == "claude_dispatch"
    assert result["evidence"]["schema"] == "OmgEvidencePack"
    assert result["business_workflow"]["verification_summary"]["state"] == "verified"
    assert result["business_workflow"]["evidence_requirements"]["tests"] == ["pytest -q tests/runtime"]
    assert result["reproducibility"]["command"].startswith("omg runtime dispatch --runtime claude")
    assert result["reproducibility"]["resume_supported"] is True


def test_runtime_dispatch_unknown_runtime_reports_deterministic_failure_category():
    result = dispatch_runtime("does-not-exist", {"goal": "x"})

    assert result["schema"] == "OmgRuntimeDispatch"
    assert result["status"] == "error"
    assert result["error_code"] == "RUNTIME_NOT_FOUND"
    assert result["failure"]["category"] == "runtime_not_found"
    assert result["failure"]["retryable"] is False
    assert result["reproducibility"]["command"].startswith("omg runtime dispatch --runtime does-not-exist")
