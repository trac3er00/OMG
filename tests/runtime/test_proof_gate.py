from __future__ import annotations

import json
from pathlib import Path

from runtime.proof_gate import evaluate_proof_gate


FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
