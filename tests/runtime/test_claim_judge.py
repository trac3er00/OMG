from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.claim_judge import evaluate_claims_for_release, judge_claim, judge_claims
from runtime.release_run_coordinator import ReleaseRunCoordinator


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_claim_judge_fails_when_artifacts_are_missing() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [],
            "trace_ids": ["trace-1"],
        }
    )

    assert result["verdict"] == "fail"
    assert any(reason["code"] == "missing_artifacts" for reason in result["reasons"])


def test_claim_judge_fails_when_trace_ids_are_missing() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": [],
        }
    )

    assert result["verdict"] == "fail"
    assert any(reason["code"] == "missing_trace_ids" for reason in result["reasons"])


def test_claim_judge_passes_with_artifacts_and_trace_ids() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_claim_judge_blocks_on_security_scan_failure() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
            "security_scans": [
                {
                    "tool": "security-check",
                    "status": "error",
                    "unresolved_risks": ["risky shell execution"],
                }
            ],
        }
    )

    assert result["verdict"] == "block"
    assert any(reason["code"] == "security_scan_failed" for reason in result["reasons"])


def test_claim_judge_accepts_v2_claim_shape() -> None:
    result = judge_claim(
        {
            "schema_version": 2,
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "evidence": {
                "artifacts": [
                    {
                        "kind": "junit",
                        "path": str(FIXTURES / "sample.junit.xml"),
                        "sha256": "abc123",
                        "parser": "junit",
                        "summary": "unit tests",
                        "trace_id": "trace-1",
                    }
                ],
                "trace_ids": ["trace-1"],
            },
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_claim_judge_blocks_when_junit_artifact_is_malformed(tmp_path: Path) -> None:
    malformed_path = tmp_path / "malformed.junit.xml"
    malformed_path.write_text("<testsuite>", encoding="utf-8")

    result = judge_claim(
        {
            "schema_version": 2,
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "evidence": {
                "artifacts": [
                    {
                        "kind": "junit",
                        "path": str(malformed_path),
                        "sha256": "abc123",
                        "parser": "junit",
                        "summary": "unit tests",
                        "trace_id": "trace-1",
                    }
                ],
                "trace_ids": ["trace-1"],
            },
        }
    )

    assert result["verdict"] == "block"
    assert any(reason["code"] == "artifact_parse_failed_junit" for reason in result["reasons"])


def test_claim_judge_accepts_valid_sarif_artifact() -> None:
    result = judge_claim(
        {
            "schema_version": 2,
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "evidence": {
                "artifacts": [
                    {
                        "kind": "sarif",
                        "path": str(FIXTURES / "sample.sarif.json"),
                        "sha256": "abc123",
                        "parser": "sarif",
                        "summary": "security scan",
                        "trace_id": "trace-1",
                    }
                ],
                "trace_ids": ["trace-1"],
            },
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_claim_judge_rejects_artifact_record_missing_sha256() -> None:
    with pytest.raises(ValueError, match="claim_artifact_missing_sha256"):
        judge_claim(
            {
                "schema_version": 2,
                "claim_type": "ready_to_ship",
                "subject": "demo",
                "evidence": {
                    "artifacts": [
                        {
                            "kind": "junit",
                            "path": ".omg/evidence/junit.xml",
                            "parser": "junit",
                            "summary": "unit tests",
                            "trace_id": "trace-1",
                        }
                    ],
                    "trace_ids": ["trace-1"],
                },
            }
        )


def test_judge_claims_resolves_evidence_pack_and_emits_artifact(tmp_path: Path) -> None:
    evidence_dir = tmp_path / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run-1"
    (evidence_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "schema_version": 2,
                "run_id": run_id,
                "trace_ids": ["trace-1"],
                "context_checksum": "ctx-1",
                "profile_version": "profile-v1",
                "intent_gate_version": "1.0.0",
                "tests": [],
                "security_scans": [],
            }
        ),
        encoding="utf-8",
    )

    result = judge_claims(tmp_path.as_posix(), claims=[{"claim_type": "tests-passed", "run_id": run_id}])

    assert result["schema"] == "ClaimJudgeResults"
    assert result["verdict"] == "pass"
    assert result["results"][0]["run_id"] == run_id
    assert isinstance(result["results"][0]["context_checksum"], str)
    assert result["results"][0]["context_checksum"]
    assert result["results"][0]["profile_version"] == "profile-v1"
    assert result["results"][0]["intent_gate_version"] == "1.0.0"
    assert (evidence_dir / f"claim-judge-{run_id}.json").exists()


def test_judge_claims_returns_insufficient_when_any_claim_blocks(tmp_path: Path) -> None:
    evidence_dir = tmp_path / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run-block"
    (evidence_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "schema_version": 2,
                "run_id": run_id,
                "trace_ids": ["trace-1"],
            }
        ),
        encoding="utf-8",
    )

    result = judge_claims(
        tmp_path.as_posix(),
        claims=[
            {
                "claim_type": "ready_to_ship",
                "run_id": run_id,
                "security_scans": [{"tool": "security-check", "status": "error"}],
            }
        ],
    )

    assert result["verdict"] == "insufficient"
    assert result["results"][0]["verdict"] == "block"


def test_judge_claims_returns_fail_when_any_claim_fails(tmp_path: Path) -> None:
    result = judge_claims(tmp_path.as_posix(), claims=[{"claim_type": "tests-passed", "run_id": "missing"}])

    assert result["verdict"] == "fail"
    assert result["results"][0]["verdict"] == "fail"


def test_judge_claims_blocks_when_council_evidence_completeness_fails(tmp_path: Path) -> None:
    run_id = "run-council-fail"
    evidence_dir = tmp_path / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "schema_version": 2,
                "run_id": run_id,
                "trace_ids": ["trace-1"],
            }
        ),
        encoding="utf-8",
    )

    council_dir = tmp_path / ".omg" / "state" / "council_verdicts"
    council_dir.mkdir(parents=True, exist_ok=True)
    (council_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "CouncilVerdicts",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "blocked",
                "verification_status": "blocked",
                "updated_at": "2026-03-08T00:00:00Z",
                "verdicts": {
                    "evidence_completeness": {
                        "verdict": "fail",
                        "findings": ["missing evidence artifacts: junit.xml"],
                        "confidence": 0.93,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = judge_claims(tmp_path.as_posix(), claims=[{"claim_type": "tests-passed", "run_id": run_id}])

    assert result["verdict"] == "insufficient"
    reasons = result["results"][0]["reasons"]
    assert any(reason["code"] == "council_evidence_incomplete" for reason in reasons)


def test_claim_judge_blocks_when_causal_chain_missing_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
        }
    )

    assert result["verdict"] == "block"
    assert any(reason["code"] == "missing_causal_chain" for reason in result["reasons"])


def test_runtime_claims_require_strict_causal_chain_metadata_by_default() -> None:
    result = judge_claim(
        {
            "claim_type": "runtime_release_ready",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
            "lock_id": "lock-1",
            "delta_summary": {"flags": []},
            "verification_status": "ok",
            "waiver_artifact_path": ".omg/evidence/waiver-lock-1.json",
        }
    )

    assert result["verdict"] == "block"
    missing_chain = [reason for reason in result["reasons"] if reason["code"] == "missing_causal_chain"]
    assert len(missing_chain) == 1
    message = str(missing_chain[0]["message"])
    assert "missing_context_checksum" in message
    assert "missing_profile_version" in message
    assert "missing_intent_gate_version" in message


def test_legacy_claims_keep_permissive_causal_chain_behavior_without_version_fields() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []
    advisories = result["evidence"]["advisories"]
    assert "claim_judge_causal_chain_missing_permissive" in advisories


def test_claim_judge_passes_when_causal_chain_includes_waiver_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
            "lock_id": "lock-1",
            "delta_summary": {"flags": ["weakened_assertions"]},
            "verification_status": "ok",
            "waiver_artifact_path": ".omg/evidence/waiver-lock-1.json",
            "context_checksum": "ctx-1",
            "profile_version": "profile-v1",
            "intent_gate_version": "1.0.0",
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_forge_evidence_claim_passes_with_waiver_artifact() -> None:
    result = judge_claim(
        {
            "claim_type": "forge_dispatch",
            "subject": "forge-vision-agent",
            "artifacts": [".omg/evidence/forge-specialists-run-1.json"],
            "trace_ids": ["forge-run-1"],
            "lock_id": "",
            "delta_summary": {"forge_dispatch": "vision", "specialists": ["data-curator"]},
            "verification_status": "ok",
            "waiver_artifact_path": ".omg/evidence/forge-specialists-run-1.json",
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_forge_evidence_claim_without_artifacts_fails() -> None:
    result = judge_claim(
        {
            "claim_type": "forge_dispatch",
            "subject": "forge-vision-agent",
            "artifacts": [],
            "trace_ids": ["forge-run-1"],
            "waiver_artifact_path": ".omg/evidence/forge-specialists-run-1.json",
        }
    )

    assert result["verdict"] == "fail"
    assert any(reason["code"] == "missing_artifacts" for reason in result["reasons"])


def test_judge_claims_exposes_profile_digest_advisory_context(tmp_path: Path) -> None:
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profile.yaml").write_text(
        "\n".join(
            [
                "preferences:",
                "  architecture_requests:",
                "    - layered architecture",
                "    - event sourcing",
                "    - cqrs",
                "    - trimmed",
                "  constraints:",
                "    Output Shape: json",
                "    keep references: true",
                "    timeout seconds: 15",
                "    retries: 2",
                "    deterministic mode: true",
                "    overflow: value",
                "user_vector:",
                "  tags:",
                "    - backend",
                "    - reliability",
                "    - verification",
                "    - security",
                "    - planning",
                "    - overflow",
                "  summary: Keep artifacts clear and tests deterministic across runs.",
                "  confidence: 0.84",
                "profile_version: profile-v11",
            ]
        ),
        encoding="utf-8",
    )

    result = judge_claims(
        tmp_path.as_posix(),
        claims=[
            {
                "claim_type": "ready_to_ship",
                "subject": "demo",
                "artifacts": [".omg/evidence/run-1.json"],
                "trace_ids": ["trace-1"],
            }
        ],
    )

    digest = result["advisory_context"]["profile_digest"]
    assert digest["profile_version"] == "profile-v11"
    assert len(digest["architecture_requests"]) == 3
    assert len(digest["constraints"]) == 5
    assert len(digest["tags"]) == 5
    assert len(digest["summary"]) <= 120
    assert result["results"][0]["advisory_context"]["profile_digest"] == digest


def test_profile_digest_hints_do_not_override_evidence_based_failures(tmp_path: Path) -> None:
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profile.yaml").write_text(
        "\n".join(
            [
                "user_vector:",
                "  summary: Always ship confidently.",
                "  confidence: 1.0",
                "profile_version: profile-v-strict",
            ]
        ),
        encoding="utf-8",
    )

    result = judge_claims(
        tmp_path.as_posix(),
        claims=[
            {
                "claim_type": "ready_to_ship",
                "subject": "demo",
                "artifacts": [],
                "trace_ids": ["trace-1"],
            }
        ],
    )

    assert result["verdict"] == "fail"
    assert result["results"][0]["verdict"] == "fail"
    assert result["advisory_context"]["profile_digest"]["profile_version"] == "profile-v-strict"


def test_claim_judge_docs_only_profile_allows_artifact_light_claims() -> None:
    result = judge_claim(
        {
            "claim_type": "docs_update",
            "subject": "proof docs",
            "artifacts": [],
            "trace_ids": ["trace-docs-1"],
            "evidence_profile": "docs-only",
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_claim_judge_release_profile_still_blocks_failed_security_scans() -> None:
    result = judge_claim(
        {
            "claim_type": "release_ready",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
            "evidence_profile": "release",
            "security_scans": [{"tool": "security-check", "status": "error"}],
        }
    )

    assert result["verdict"] == "block"
    assert any(reason["code"] == "security_scan_failed" for reason in result["reasons"])


def test_claim_judge_missing_or_empty_evidence_profile_fails_closed() -> None:
    for profile in (None, ""):
        payload = {
            "claim_type": "docs_update",
            "subject": "proof docs",
            "artifacts": [],
            "trace_ids": ["trace-docs-1"],
        }
        if profile is not None:
            payload["evidence_profile"] = profile

        result = judge_claim(payload)
        assert result["verdict"] == "fail"
        assert any(reason["code"] == "missing_artifacts" for reason in result["reasons"])


def test_evaluate_claims_for_release_blocks_when_claim_judge_verdict_is_insufficient(tmp_path: Path) -> None:
    run_id = "run-release-block"
    result = evaluate_claims_for_release(
        project_dir=tmp_path.as_posix(),
        run_id=run_id,
        claims=[{"claim_type": "release_ready", "run_id": run_id, "evidence_profile": "release"}],
    )

    assert result["status"] == "blocked"
    assert result["authority"] == "claim_judge"
    assert result["claim_judge_verdict"] in {"fail", "insufficient"}


def test_release_run_coordinator_finalize_blocks_when_claim_judge_blocks(tmp_path: Path) -> None:
    coordinator = ReleaseRunCoordinator(str(tmp_path))
    begin = coordinator.begin(
        cli_run_id="run-finalize-block",
        release_evidence={
            "claims": [
                {
                    "claim_type": "release_ready",
                    "run_id": "run-finalize-block",
                    "evidence_profile": "release",
                }
            ]
        },
    )

    result = coordinator.finalize(
        run_id=str(begin["run_id"]),
        status="ok",
        blockers=[],
        evidence_links=[],
    )

    assert result["status"] == "blocked"
    verification = json.loads(
        (tmp_path / ".omg" / "state" / "verification_controller" / "run-finalize-block.json").read_text(
            encoding="utf-8"
        )
    )
    assert "claim_judge_verdict" in " ".join(str(token) for token in verification.get("blockers", []))
