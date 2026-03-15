from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import cast

import pytest

from runtime.evidence_requirements import FULL_REQUIREMENTS
from runtime.proof_gate import evaluate_proof_gate, production_gate


FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def _seed_release_readiness_fixtures(output_root: Path) -> None:
    prepare = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare-release-proof-fixtures.py"), "--output-root", str(output_root)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_proof_gate_fails_when_claims_are_empty() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
        }
    )

    assert result["verdict"] == "fail"
    assert "proof_gate_missing_claims" in result["blockers"]


def test_proof_gate_fails_when_proof_chain_has_blockers() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "error", "blockers": ["proof_chain_missing_trace_id"], "trace_id": "trace-1"},
        }
    )

    assert result["verdict"] == "fail"
    assert any(str(item).startswith("proof_gate_proof_chain") for item in result["blockers"])


def test_proof_gate_passes_with_clean_chain_and_claims() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "evidence": {
                        "artifacts": [
                            {
                                "kind": "junit",
                                "path": str(FIXTURES / "sample.junit.xml"),
                                "sha256": "abc123",
                                "parser": "junit",
                                "summary": "junit",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "coverage",
                                "path": str(FIXTURES / "sample_coverage.xml"),
                                "sha256": "abc124",
                                "parser": "coverage",
                                "summary": "coverage",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "sarif",
                                "path": str(FIXTURES / "sample.sarif.json"),
                                "sha256": "abc125",
                                "parser": "sarif",
                                "summary": "security scan",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "browser_trace",
                                "path": str(FIXTURES / "sample_browser_trace.json"),
                                "sha256": "abc126",
                                "parser": "playwright",
                                "summary": "browser trace",
                                "trace_id": "trace-1",
                            },
                        ],
                        "trace_ids": ["trace-1"],
                    },
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
        }
    )

    assert result["verdict"] == "pass"
    assert result["blockers"] == []


def test_proof_gate_fails_with_specific_blocker_when_junit_is_malformed(tmp_path: Path) -> None:
    malformed_junit = tmp_path / "bad.junit.xml"
    malformed_junit.write_text("<testsuite>", encoding="utf-8")

    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "evidence": {
                        "artifacts": [
                            {
                                "kind": "junit",
                                "path": str(malformed_junit),
                                "sha256": "abc123",
                                "parser": "junit",
                                "summary": "junit",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "coverage",
                                "path": str(FIXTURES / "sample_coverage.xml"),
                                "sha256": "abc124",
                                "parser": "coverage",
                                "summary": "coverage",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "sarif",
                                "path": str(FIXTURES / "sample.sarif.json"),
                                "sha256": "abc125",
                                "parser": "sarif",
                                "summary": "security scan",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "browser_trace",
                                "path": str(FIXTURES / "sample_browser_trace.json"),
                                "sha256": "abc126",
                                "parser": "playwright",
                                "summary": "browser trace",
                                "trace_id": "trace-1",
                            },
                        ],
                        "trace_ids": ["trace-1"],
                    },
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
        }
    )

    assert result["verdict"] == "fail"
    assert "proof_gate_artifact_parse_failed_junit" in result["blockers"]


def test_proof_gate_accepts_v1_evidence_payload() -> None:
    payload = json.loads((FIXTURES / "evidence_v1_sample.json").read_text(encoding="utf-8"))
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "evidence_pack": payload,
        }
    )

    assert "proof_gate_invalid_evidence_pack" not in result["blockers"]
    assert "proof_gate_unsupported_evidence_schema_version" not in result["blockers"]


def test_proof_gate_accepts_v2_evidence_payload() -> None:
    payload = json.loads((FIXTURES / "evidence_v2_sample.json").read_text(encoding="utf-8"))
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "evidence": {
                        "artifacts": [
                            {
                                "kind": "junit",
                                "path": ".omg/evidence/junit.xml",
                                "sha256": "abc123",
                                "parser": "junit",
                                "summary": "junit",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "coverage",
                                "path": ".omg/evidence/coverage.xml",
                                "sha256": "abc124",
                                "parser": "coverage",
                                "summary": "coverage",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "sarif",
                                "path": ".omg/evidence/security-check.sarif",
                                "sha256": "abc125",
                                "parser": "sarif",
                                "summary": "security scan",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "browser_trace",
                                "path": ".omg/evidence/trace.zip",
                                "sha256": "abc126",
                                "parser": "playwright",
                                "summary": "browser trace",
                                "trace_id": "trace-1",
                            },
                        ],
                        "trace_ids": ["trace-1"],
                    },
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "evidence_pack": payload,
        }
    )

    assert "proof_gate_invalid_evidence_pack" not in result["blockers"]
    assert "proof_gate_unsupported_evidence_schema_version" not in result["blockers"]


def test_proof_gate_accepts_v2_evidence_payload_with_optional_sibling_fields() -> None:
    payload = json.loads((FIXTURES / "evidence_v2_sample.json").read_text(encoding="utf-8"))
    payload["claims"] = [{"claim_type": "release_ready", "trace_ids": ["trace-1"]}]
    payload["test_delta"] = {"changed": ["runtime/proof_chain.py"]}
    payload["browser_evidence_path"] = ".omg/evidence/playwright-adapter-run-1.json"
    payload["repro_pack_path"] = ".omg/evidence/repro-pack-run-1.json"
    payload["context_checksum"] = "ctx-deterministic"
    payload["profile_version"] = "profile-v31"
    payload["intent_gate_version"] = "1.3.0"
    payload["intent_gate_state"] = {"path": ".omg/state/intent_gate/run-1.json", "run_id": "run-1"}
    payload["profile_digest"] = {"path": ".omg/state/profile.yaml", "profile_version": "profile-v31"}
    payload["session_health_state"] = {"path": ".omg/state/session_health/run-1.json", "run_id": "run-1"}
    payload["council_verdicts"] = {"path": ".omg/state/council_verdicts/run-1.json", "run_id": "run-1"}
    payload["forge_starter_proof"] = {"path": ".omg/evidence/forge-specialists-run-1.json", "run_id": "run-1"}

    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "evidence_pack": payload,
        }
    )

    assert "proof_gate_invalid_evidence_pack" not in result["blockers"]
    assert "proof_gate_unsupported_evidence_schema_version" not in result["blockers"]
    assert result["evidence_summary"]["proof_chain_status"] == "ok"


def test_proof_gate_accepts_browser_cli_trace_linked_by_claims() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "browser-trace.zip"],
                    "trace_ids": ["trace-browser-cli"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-browser-cli"},
            "eval_output": {"trace_id": "trace-browser-cli", "status": "ok"},
            "browser_evidence": {
                "schema": "BrowserEvidence",
                "artifacts": {"trace": ".omg/evidence/browser-trace.zip"},
                "metadata": {"trace_id": "trace-browser-cli"},
            },
        }
    )

    assert "proof_gate_browser_trace_not_linked_by_claims" not in result["blockers"]
    assert "proof_gate_browser_trace_mismatch" not in result["blockers"]


def test_proof_gate_fails_without_lock_evidence_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "test_delta": {"flags": []},
        }
    )

    assert result["verdict"] == "fail"
    assert "proof_gate_missing_lock_evidence" in result["blockers"]


def test_proof_gate_requires_waiver_artifact_for_weakened_delta_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "test_intent_lock": {"status": "ok", "lock_id": "lock-1"},
            "test_delta": {"flags": ["weakened_assertions"]},
        }
    )

    assert result["verdict"] == "fail"
    assert "proof_gate_missing_waiver_artifact" in result["blockers"]


def test_forge_proof_gate_passes_with_complete_evidence() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "forge_dispatch",
                    "artifacts": [
                        "junit.xml", "coverage.xml", "scan.sarif", "trace.zip",
                        ".omg/evidence/forge-specialists-run-1.json",
                    ],
                    "trace_ids": ["forge-run-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "forge-run-1"},
        }
    )

    assert result["verdict"] == "pass"


def test_forge_proof_gate_fails_without_evidence() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "forge_dispatch",
                    "artifacts": [],
                    "trace_ids": [],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "forge-run-1"},
        }
    )

    assert result["verdict"] == "fail"
    assert any("missing" in b for b in result["blockers"])


def test_proof_gate_docs_only_profile_does_not_require_release_artifacts() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "docs_update",
                    "artifacts": ["docs/proof.md"],
                    "trace_ids": ["trace-docs-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-docs-1"},
            "evidence_profile": "docs-only",
        }
    )

    assert result["verdict"] == "pass"
    assert "proof_gate_missing_artifact_sarif" not in result["blockers"]
    assert "proof_gate_missing_artifact_browser_trace" not in result["blockers"]


def test_proof_gate_release_profile_requires_full_artifact_set() -> None:
    result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": ["junit.xml", "coverage.xml"],
                    "trace_ids": ["trace-release-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-release-1"},
            "evidence_profile": "release",
        }
    )

    assert result["verdict"] == "fail"
    assert "proof_gate_missing_artifact_sarif" in result["blockers"]
    assert "proof_gate_missing_artifact_browser_trace" in result["blockers"]


def test_proof_gate_missing_or_empty_evidence_profile_fails_closed_to_full_requirements() -> None:
    for profile in (None, ""):
        payload: dict[str, object] = {
            "claims": [
                {
                    "claim_type": "docs_update",
                    "artifacts": ["docs/proof.md"],
                    "trace_ids": ["trace-default-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-default-1"},
        }
        if profile is not None:
            payload["evidence_profile"] = profile

        result = evaluate_proof_gate(payload)
        assert result["verdict"] == "fail"
        assert "proof_gate_missing_artifact_junit" in result["blockers"]
        assert result["evidence_summary"]["evidence_requirements"] == list(FULL_REQUIREMENTS)


def test_proof_gate_strict_release_chain_passes_with_lock_provenance_and_mutation_waiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_release_readiness_fixtures(tmp_path)
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")

    evidence_root = tmp_path / ".omg" / "evidence"
    junit_path = evidence_root / "junit.xml"
    coverage_path = evidence_root / "coverage.xml"
    sarif_path = evidence_root / "results.sarif"
    browser_trace_path = evidence_root / "browser_trace.json"

    security_evidence = cast(
        dict[str, object],
        json.loads((evidence_root / "security-check.json").read_text(encoding="utf-8")),
    )
    lock_state = cast(
        dict[str, object],
        json.loads(
        (tmp_path / ".omg" / "state" / "test-intent-lock" / "lock-1.json").read_text(encoding="utf-8")
        ),
    )
    proof_result = evaluate_proof_gate(
        {
            "claims": [
                {
                    "claim_type": "release_ready",
                    "lock_id": "lock-1",
                    "evidence": {
                        "artifacts": [
                            {
                                "kind": "junit",
                                "path": str(junit_path),
                                "sha256": _sha256(junit_path),
                                "parser": "junit",
                                "summary": "release junit",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "coverage",
                                "path": str(coverage_path),
                                "sha256": _sha256(coverage_path),
                                "parser": "coverage",
                                "summary": "release coverage",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "sarif",
                                "path": str(sarif_path),
                                "sha256": _sha256(sarif_path),
                                "parser": "sarif",
                                "summary": "release security",
                                "trace_id": "trace-1",
                            },
                            {
                                "kind": "browser_trace",
                                "path": str(browser_trace_path),
                                "sha256": _sha256(browser_trace_path),
                                "parser": "playwright",
                                "summary": "release browser trace",
                                "trace_id": "trace-1",
                            },
                        ],
                        "trace_ids": ["trace-1"],
                    },
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
            "security_evidence": security_evidence,
            "browser_evidence": {
                "schema": "BrowserEvidence",
                "artifacts": {"trace": str(browser_trace_path)},
                "metadata": {"trace_id": "trace-1"},
            },
            "test_intent_lock": lock_state,
            "test_delta": {
                "flags": ["weakened_assertions"],
                "lock_id": "lock-1",
                "waiver_artifact": {
                    "artifact_path": ".omg/evidence/waiver-tests-lock-1.json",
                    "reason": "approved release fixture",
                },
            },
            "evidence_profile": "release",
        }
    )

    assert proof_result["verdict"] == "pass"
    assert proof_result["blockers"] == []
    assert proof_result["evidence_summary"]["trace_id"] == "trace-1"
    assert proof_result["evidence_summary"]["has_lock_evidence"] is True
    assert proof_result["evidence_summary"]["has_waiver_artifact"] is True
    assert proof_result["evidence_summary"]["required_artifacts"] == ["junit", "coverage", "sarif", "browser_trace"]


def test_production_gate_fails_when_proof_primitives_missing() -> None:
    result = production_gate({})

    assert result["status"] == "blocked"
    assert "production_gate_missing_claim_judge" in result["blockers"]
    assert "production_gate_missing_test_intent_lock" in result["blockers"]


def test_production_gate_passes_when_release_security_proof_complete() -> None:
    result = production_gate(
        {
            "claim_judge": {"status": "allowed", "claim_judge_verdict": "pass"},
            "proof_gate": {"verdict": "pass", "blockers": []},
            "test_intent_lock": {"status": "ok", "lock_id": "lock-1"},
        }
    )

    assert result["status"] == "ok"
