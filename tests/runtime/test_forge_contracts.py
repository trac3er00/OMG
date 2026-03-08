from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.forge_contracts import build_forge_evidence, load_forge_mvp, validate_forge_job


def _valid_job() -> dict[str, object]:
    return {
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
