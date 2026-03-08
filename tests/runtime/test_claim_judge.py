from __future__ import annotations

from pathlib import Path

import pytest

from runtime.claim_judge import judge_claim


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
