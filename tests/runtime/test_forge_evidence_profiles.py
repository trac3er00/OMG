from __future__ import annotations

from typing import Any

from lab.pipeline import run_pipeline
from runtime.compliance_governor import evaluate_release_compliance
from runtime.evidence_requirements import requirements_for_profile
from runtime.forge_agents import dispatch_specialists


def _job(domain: str, specialists: list[str]) -> dict[str, Any]:
    return {
        "domain": domain,
        "dataset": {
            "name": f"{domain}-dataset",
            "license": "apache-2.0",
            "source": "internal-curated",
        },
        "base_model": {
            "name": "distill-base-v1",
            "source": "approved-registry",
            "allow_distill": True,
        },
        "target_metric": 0.8,
        "specialists": specialists,
    }


def test_labs_loop_emits_signed_forge_artifact_flows(tmp_path) -> None:
    result = dispatch_specialists(
        _job("vision", ["data-curator", "training-architect", "simulator-engineer"]),
        str(tmp_path),
        run_id="labs-signed-run",
    )

    assert result["status"] == "ok"
    contracts = result["artifact_contracts"]
    for contract_name in ("dataset_lineage", "model_card", "checkpoint_hash"):
        contract = contracts[contract_name]
        assert contract["status"] == "signed"
        assert contract["signer_key_id"] != ""
        assert isinstance(contract.get("attestation"), dict)
    assert "simulator_episode_evidence" in result


def test_missing_domain_pack_requirement_blocks_promotion() -> None:
    result = run_pipeline(_job("health", ["data-curator", "training-architect"]))

    assert result["promotion_ready"] is False
    assert any("missing required approvals" in blocker for blocker in result["promotion_blockers"])
    gate = result["domain_pack_gate"]
    assert gate["domain"] == "health"
    assert "human-review" in gate["missing_approvals"]


def test_domain_profiles_forge_vision_health_transposition_are_enforced() -> None:
    vision = run_pipeline(_job("vision", ["data-curator", "training-architect", "simulator-engineer"]))
    health = run_pipeline(_job("health", ["data-curator", "training-architect"]))
    algorithms = run_pipeline(_job("algorithms", ["training-architect"]))

    assert vision["domain_pack_gate"]["evidence_profile"] == "forge-vision"
    assert health["domain_pack_gate"]["evidence_profile"] == "health-flow"
    assert algorithms["domain_pack_gate"]["evidence_profile"] == "transposition-flow"
    assert set(requirements_for_profile("forge-vision")).issuperset({"signed_lineage", "signed_model_card"})
    assert "human-review" in requirements_for_profile("health-flow")
    assert "benchmark-harness" in requirements_for_profile("transposition-flow")


def test_security_audit_profile_requires_signed_artifacts(tmp_path) -> None:
    reqs = requirements_for_profile("security-audit")
    assert "signed_lineage" in reqs
    assert "signed_model_card" in reqs
    assert "signed_checkpoint" in reqs

    decision = evaluate_release_compliance(
        project_dir=str(tmp_path),
        run_id="security-audit-unsigned",
        release_evidence={
            "artifact": {
                "id": ".omg/evidence/unsigned.json",
                "checksum": "a" * 64,
                "attestation": None,
                "signer": "",
                "artifact_contracts": {
                    "dataset_lineage": {"status": "signed"},
                    "model_card": {"status": "signed"},
                    "checkpoint_hash": {"status": "signed"},
                },
            }
        },
    )
    assert decision["status"] == "blocked"
