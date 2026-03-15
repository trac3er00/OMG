from __future__ import annotations

from unittest.mock import patch

from runtime.compliance_governor import evaluate_release_compliance, production_gate


_SUBJECT_SHA256 = "a" * 64


def _verified(action: str) -> dict[str, object]:
    return {
        "action": action,
        "reason": f"{action}-reason",
        "algorithm": "ed25519-minisign",
        "key_id": "1f5fe64ec2f8c901",
        "subject_sha256": _SUBJECT_SHA256,
    }


def _evaluate(release_evidence: dict[str, object] | None) -> dict[str, object]:
    evidence = release_evidence
    if isinstance(evidence, dict):
        evidence = {
            "claim_judge": {"status": "allowed", "claim_judge_verdict": "pass"},
            "proof_gate": {"verdict": "pass", "blockers": []},
            "test_intent_lock": {"status": "ok", "lock_id": "lock-1"},
            **evidence,
        }
    with patch(
        "runtime.compliance_governor.evaluate_claims_for_release",
        return_value={"status": "allowed", "reason": "ok", "claim_judge_verdict": "pass"},
    ):
        return evaluate_release_compliance(project_dir=".", run_id="", release_evidence=evidence)


def test_missing_release_evidence_blocks() -> None:
    result = _evaluate(None)
    assert result["status"] == "blocked"
    assert result["reason"] == "no release evidence supplied"


def test_missing_artifact_blocks() -> None:
    result = _evaluate({})
    assert result["status"] == "blocked"
    assert result["reason"] == "no artifact supplied"


def test_artifact_dict_missing_blocks() -> None:
    result = _evaluate({"artifact": "not-a-dict"})
    assert result["status"] == "blocked"
    assert result["reason"] == "no artifact supplied"


def test_allow_action_passes() -> None:
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("allow")):
        result = _evaluate({"artifact": {"id": "ok"}})
    assert result["status"] == "allowed"
    assert result["authority"] == "release"


def test_deny_action_blocks() -> None:
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("deny")):
        result = _evaluate({"artifact": {"id": "bad"}})
    assert result["status"] == "blocked"
    assert result["authority"] == "artifact"


def test_ask_without_approval_blocks() -> None:
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("ask")):
        result = _evaluate({"artifact": {"id": "needs-approval"}})
    assert result["status"] == "blocked"
    assert result["reason"] == "ask result requires signed approval artifact"


def test_ask_with_valid_approval_passes() -> None:
    approval_artifact = {
        "artifact_digest": _SUBJECT_SHA256,
        "action": "allow",
        "scope": "release",
        "reason": "manual approval",
        "signer_key_id": "1f5fe64ec2f8c901",
        "issued_at": "2026-03-10T00:00:00+00:00",
        "signature": "sig",
    }
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("ask")):
        with patch("runtime.compliance_governor.verify_approval_artifact", return_value={"valid": True, "reason": "verified"}):
            result = _evaluate({"artifact": {"id": "needs-approval"}, "approval_artifact": approval_artifact})
    assert result["status"] == "allowed"
    assert result["approval_authority"] == "1f5fe64ec2f8c901"


def test_ask_with_invalid_approval_blocks() -> None:
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("ask")):
        with patch("runtime.compliance_governor.verify_approval_artifact", return_value={"valid": False, "reason": "invalid"}):
            result = _evaluate(
                {
                    "artifact": {"id": "needs-approval"},
                    "approval_artifact": {"artifact_digest": _SUBJECT_SHA256},
                }
            )
    assert result["status"] == "blocked"
    assert result["reason"] == "ask result requires signed approval artifact"


def test_ask_with_approval_path_passes() -> None:
    loaded_approval = {
        "artifact_digest": _SUBJECT_SHA256,
        "action": "allow",
        "scope": "release",
        "reason": "path approval",
        "signer_key_id": "1f5fe64ec2f8c901",
        "issued_at": "2026-03-10T00:00:00+00:00",
        "signature": "sig",
    }
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("ask")):
        with patch(
            "runtime.compliance_governor.load_approval_artifact_from_path",
            return_value={"valid": True, "reason": "verified", "approval": loaded_approval},
        ):
            result = _evaluate(
                {
                    "artifact": {"id": "needs-approval"},
                    "approval_artifact_path": "/tmp/approval.json",
                }
            )
    assert result["status"] == "allowed"
    assert result["approval_reason"] == "path approval"


def test_audit_fields_present_on_allow() -> None:
    with patch("runtime.compliance_governor.verify_artifact", return_value=_verified("allow")):
        result = _evaluate({"artifact": {"id": "ok"}})
    assert result["artifact_alg"] == "ed25519-minisign"
    assert result["artifact_key_id"] == "1f5fe64ec2f8c901"
    assert result["artifact_subject_sha256"] == _SUBJECT_SHA256
    assert result["artifact_verdict"] == "allow"


def test_production_gate_blocks_when_required_primitives_missing() -> None:
    result = production_gate({"proof_gate": {"verdict": "pass", "blockers": []}})
    assert result["status"] == "blocked"
    assert "production_gate_missing_claim_judge" in result["blockers"]
    assert "production_gate_missing_test_intent_lock" in result["blockers"]


def test_production_gate_passes_with_complete_primitives() -> None:
    result = production_gate(
        {
            "claim_judge": {"status": "allowed", "claim_judge_verdict": "pass"},
            "proof_gate": {"verdict": "pass", "blockers": []},
            "test_intent_lock": {"status": "ok", "lock_id": "lock-1"},
        }
    )
    assert result["status"] == "ok"
