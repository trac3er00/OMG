from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.forge_contracts import ADAPTER_REGISTRY, build_forge_evidence, build_stage_evidence, load_forge_mvp, validate_forge_job


def _valid_job() -> dict[str, object]:
    return {
        "domain": "vision",
        "dataset": {
            "name": "forge-mvp",
            "license": "apache-2.0",
            "source": "internal-curated",
        },
        "base_model": {
            "name": "distill-base-v1",
            "source": "approved-registry",
            "allow_distill": True,
        },
        "target_metric": 0.8,
        "simulated_metric": 0.9,
    }


def test_load_forge_mvp_exposes_bounded_contract_fields() -> None:
    contract = load_forge_mvp()

    assert contract["axolotl_hook"] == "lab.axolotl_adapter.run"
    assert contract["pybullet_hook"] == "lab.pybullet_adapter.run"
    assert contract["labs_only"] is True
    assert "job_schema" in contract
    assert "evaluation_schema" in contract
    assert "specialist_dispatch" in contract
    assert contract["evidence_output_path"] == ".omg/evidence/forge-<run_id>.json"
    assert "stage_aliases" in contract
    stage_aliases = cast(dict[str, str], contract["stage_aliases"])
    assert stage_aliases["security_review"] == "regression_test"


def test_validate_forge_job_delegates_policy_and_checks_schema() -> None:
    ok, reason = validate_forge_job(_valid_job())
    assert ok is True
    assert reason == "ok"

    missing_model_name = _valid_job()
    assert isinstance(missing_model_name["base_model"], dict)
    del missing_model_name["base_model"]["name"]

    ok, reason = validate_forge_job(missing_model_name)
    assert ok is False
    assert reason == "base_model.name missing"


def test_validate_forge_job_rejects_missing_target_metric() -> None:
    job = _valid_job()
    del job["target_metric"]

    ok, reason = validate_forge_job(job)

    assert ok is False
    assert reason == "target_metric missing or invalid"


def test_build_forge_evidence_writes_atomic_json(tmp_path: Path) -> None:
    result = {
        "status": "ready",
        "stage": "complete",
        "published": False,
        "evaluation_report": {
            "created_at": "2026-03-08T00:00:00+00:00",
            "metric": 0.9,
            "target_metric": 0.8,
            "passed": True,
            "notes": "",
        },
    }

    path = build_forge_evidence(str(tmp_path), "run-123", _valid_job(), result)
    evidence_path = tmp_path / ".omg" / "evidence" / "forge-run-123.json"
    tmp_file = tmp_path / ".omg" / "evidence" / "forge-run-123.json.tmp"

    assert path == str(evidence_path)
    assert evidence_path.exists()
    assert not tmp_file.exists()

    raw_payload = cast(object, json.loads(evidence_path.read_text(encoding="utf-8")))
    assert isinstance(raw_payload, dict)
    payload = cast(dict[str, object], raw_payload)
    assert payload["schema"] == "ForgeMVPEvidence"
    assert payload["schema_version"] == "1.0.0"
    assert payload["run_id"] == "run-123"
    assert payload["status"] == "ready"
    result_payload = cast(dict[str, object], payload["result"])
    assert result_payload["stage"] == "complete"


def test_build_forge_evidence_includes_proof_backed_starter_fields(tmp_path: Path) -> None:
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-proof-1", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    assert payload["labs_only"] is True
    assert payload["proof_backed"] is True
    assert isinstance(payload.get("specialist"), str)
    assert isinstance(payload.get("domain"), str)


def test_build_forge_evidence_includes_release_ready_metadata(tmp_path: Path) -> None:
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-meta-1", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    assert "context_checksum" in payload, "context_checksum missing from evidence"
    assert str(payload["context_checksum"]).strip(), "context_checksum must be non-empty"
    assert "profile_version" in payload, "profile_version missing from evidence"
    assert str(payload["profile_version"]).strip(), "profile_version must be non-empty"
    assert "intent_gate_version" in payload, "intent_gate_version missing from evidence"
    assert str(payload["intent_gate_version"]).strip(), "intent_gate_version must be non-empty"


def test_build_forge_evidence_includes_causal_chain_stub(tmp_path: Path) -> None:
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-chain-1", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    assert "causal_chain" in payload
    chain = cast(dict[str, object], payload["causal_chain"])
    has_lock = bool(str(chain.get("lock_id", "")).strip())
    has_waiver = bool(str(chain.get("waiver_artifact_path", "")).strip())
    assert has_lock or has_waiver


def test_load_forge_mvp_includes_starter_templates() -> None:
    contract = load_forge_mvp()
    assert "starter_templates" in contract
    templates = cast(dict[str, object], contract["starter_templates"])
    assert "vision-agent" in templates
    assert "robotics" in templates


def test_load_forge_mvp_includes_adapter_registry() -> None:
    contract = load_forge_mvp()
    assert "adapter_registry" in contract
    registry = cast(dict[str, object], contract["adapter_registry"])
    assert "axolotl" in registry
    assert "pybullet" in registry
    assert "gazebo" in registry
    assert "isaac_gym" in registry


def test_adapter_registry_has_required_fields() -> None:
    for name, entry in ADAPTER_REGISTRY.items():
        assert "kind" in entry, f"{name} missing kind"
        assert "module" in entry, f"{name} missing module"
        assert "hook" in entry, f"{name} missing hook"
        assert "specialist" in entry, f"{name} missing specialist"
        assert str(entry["kind"]) in ("training", "simulator")


def test_adapter_registry_has_single_primary_simulator() -> None:
    primaries = [
        name for name, entry in ADAPTER_REGISTRY.items()
        if entry.get("primary") is True and str(entry.get("kind")) == "simulator"
    ]
    assert primaries == ["pybullet"]


def test_build_stage_evidence_includes_adapter_evidence_when_provided() -> None:
    from time import monotonic

    adapter_ev: list[dict[str, object]] = [{"adapter": "pybullet", "status": "invoked", "kind": "simulator"}]
    result = build_stage_evidence(
        stage="evaluate",
        run_id="run-adapter-1",
        status="success",
        started_at_ms=monotonic(),
        defense_snapshot={},
        session_health_snapshot={},
        artifacts=[],
        adapter_evidence=adapter_ev,
    )
    assert "adapter_evidence" in result
    assert result["adapter_evidence"] == adapter_ev


def test_build_stage_evidence_omits_adapter_evidence_when_none() -> None:
    from time import monotonic

    result = build_stage_evidence(
        stage="data_prepare",
        run_id="run-adapter-2",
        status="success",
        started_at_ms=monotonic(),
        defense_snapshot={},
        session_health_snapshot={},
        artifacts=[],
    )
    assert "adapter_evidence" not in result


def test_load_forge_mvp_job_schema_includes_adapter_optional_fields() -> None:
    contract = load_forge_mvp()
    schema = cast(dict[str, object], contract["job_schema"])
    optional = cast(list[str], schema["optional"])
    assert "simulator_backend" in optional
    assert "require_backend" in optional


def test_load_forge_mvp_includes_cybersecurity_specialist_contract() -> None:
    contract = load_forge_mvp()
    specialist_contracts = cast(dict[str, object], contract["specialist_contracts"])
    cybersecurity = cast(dict[str, object], specialist_contracts["forge-cybersecurity"])

    assert cybersecurity["labs_only"] is True
    assert cybersecurity["allowed_domains"] == ["cybersecurity"]
    assert cybersecurity["evidence_profile"] == "forge-run"
    assert cybersecurity["stage_alias"] == "regression_test"


def test_build_forge_evidence_includes_artifact_contracts(tmp_path: Path) -> None:
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-artifacts-1", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    assert "artifact_contracts" in payload, "artifact_contracts missing from evidence"
    contracts = cast(dict[str, object], payload["artifact_contracts"])
    assert "dataset_lineage" in contracts, "dataset_lineage missing from artifact_contracts"
    assert "model_card" in contracts, "model_card missing from artifact_contracts"
    assert "checkpoint_hash" in contracts, "checkpoint_hash missing from artifact_contracts"
    assert "regression_scoreboard" in contracts, "regression_scoreboard missing from artifact_contracts"
    assert "promotion_decision" in contracts, "promotion_decision missing from artifact_contracts"


def test_build_forge_evidence_artifact_contracts_have_status(tmp_path: Path) -> None:
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-artifacts-2", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    contracts = cast(dict[str, object], payload["artifact_contracts"])
    for key, contract in contracts.items():
        contract_dict = cast(dict[str, object], contract)
        assert "status" in contract_dict, f"artifact_contracts.{key} missing status field"
        assert str(contract_dict["status"]).strip(), f"artifact_contracts.{key} status must be non-empty"


def test_build_forge_evidence_artifact_contracts_no_placeholders(tmp_path: Path) -> None:
    """Verify artifact contracts do NOT have placeholder status in the promotion path."""
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-no-placeholders", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    contracts = cast(dict[str, object], payload["artifact_contracts"])
    for key, contract in contracts.items():
        contract_dict = cast(dict[str, object], contract)
        # Promotion decision might be 'pending' or 'ok', but others should have concrete status
        if key == "promotion_decision":
            continue
        assert contract_dict["status"] != "placeholder", f"artifact_contracts.{key} still has placeholder status"


def test_build_forge_evidence_artifact_contracts_have_concrete_fields(tmp_path: Path) -> None:
    """Verify artifact contracts have concrete schema requirements."""
    result = {"status": "ready", "stage": "complete", "published": False}
    path = build_forge_evidence(str(tmp_path), "run-concrete-fields", _valid_job(), result)
    payload = cast(dict[str, object], json.loads(Path(path).read_text(encoding="utf-8")))

    contracts = cast(dict[str, object], payload["artifact_contracts"])
    
    # Dataset lineage should have lineage_hash or similar
    assert "lineage_hash" in contracts["dataset_lineage"]
    
    # Model card should have model_id
    assert "model_id" in contracts["model_card"]
    
    # Checkpoint hash should have sha256
    assert "sha256" in contracts["checkpoint_hash"]
    
    # Regression scoreboard should have score
    assert "score" in contracts["regression_scoreboard"]
    
    # Promotion decision should have decision_id
    assert "decision_id" in contracts["promotion_decision"]
