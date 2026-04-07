from __future__ import annotations

from importlib import import_module
from pathlib import Path

from runtime.claim_judge import judge_claim


compute_score = import_module("runtime.proof_score").compute_score
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_compute_score_returns_weak_zero_for_empty_evidence() -> None:
    result = compute_score([])

    assert result["score"] == 0
    assert result["band"] == "weak"
    assert result["breakdown"] == {
        "completeness": 0,
        "validity": 0,
        "diversity": 0,
        "traceability": 0,
    }


def test_compute_score_stays_in_zero_to_hundred_range() -> None:
    scenarios = [
        [],
        [{"type": "junit"}],
        [{"type": "junit", "valid": False}],
        [
            {"type": "junit", "path": "reports/junit.xml"},
            {"type": "coverage", "path": "reports/coverage.json"},
            {"type": "sarif", "path": "reports/scan.sarif", "valid": False},
            {"type": "browser_trace", "path": "reports/trace.zip"},
            {"type": "browser_trace", "path": "reports/trace-2.zip"},
        ],
    ]

    for evidence_list in scenarios:
        result = compute_score(evidence_list)
        assert 0 <= result["score"] <= 100


def test_compute_score_is_deterministic_for_same_input() -> None:
    evidence_list = [
        {"type": "junit", "path": "reports/junit.xml"},
        {"type": "coverage"},
        {"type": "sarif", "valid": False},
    ]

    first = compute_score(evidence_list)
    for _ in range(100):
        assert compute_score(evidence_list) == first


def test_compute_score_uses_canonical_band_thresholds() -> None:
    weak = compute_score([{"valid": False}])
    developing = compute_score([{"type": "junit", "valid": False}])
    strong = compute_score([{"type": "junit", "path": "reports/junit.xml"}])
    complete = compute_score(
        [
            {"type": "junit", "path": "reports/junit.xml"},
            {"type": "coverage", "path": "reports/coverage.json"},
        ]
    )

    assert weak["score"] < 40
    assert weak["band"] == "weak"
    assert 40 <= developing["score"] < 65
    assert developing["band"] == "developing"
    assert 65 <= strong["score"] < 85
    assert strong["band"] == "strong"
    assert complete["score"] >= 85
    assert complete["band"] == "complete"


def test_invalid_evidence_reduces_validity_component() -> None:
    valid = compute_score([{"type": "junit"}])
    invalid = compute_score([{"type": "junit", "valid": False}])

    assert invalid["breakdown"]["validity"] < valid["breakdown"]["validity"]
    assert invalid["score"] < valid["score"]


def test_multiple_types_increase_diversity_component() -> None:
    single_type = compute_score(
        [
            {"type": "junit"},
            {"type": "junit"},
        ]
    )
    multiple_types = compute_score(
        [
            {"type": "junit"},
            {"type": "coverage"},
        ]
    )

    assert (
        multiple_types["breakdown"]["diversity"] > single_type["breakdown"]["diversity"]
    )
    assert multiple_types["score"] > single_type["score"]


def test_path_backed_evidence_increases_traceability_component() -> None:
    no_path = compute_score([{"type": "junit"}])
    with_path = compute_score([{"type": "junit", "path": "reports/junit.xml"}])

    assert no_path["breakdown"]["traceability"] == 0
    assert with_path["breakdown"]["traceability"] > no_path["breakdown"]["traceability"]
    assert with_path["score"] > no_path["score"]


def test_breakdown_matches_expected_component_values() -> None:
    result = compute_score(
        [
            {"type": "junit", "path": "reports/junit.xml"},
            {"type": "coverage", "valid": False},
        ]
    )

    assert result == {
        "score": 75,
        "band": "strong",
        "breakdown": {
            "completeness": 40,
            "validity": 15,
            "diversity": 15,
            "traceability": 5,
        },
    }


def test_claim_judge_remains_backward_compatible_with_verdict_field() -> None:
    result = judge_claim(
        {
            "claim_type": "ready_to_ship",
            "subject": "demo",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["trace-1"],
        }
    )

    assert result["verdict"] == "pass"


def test_claim_judge_adds_optional_proof_score_field() -> None:
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
                    },
                    {
                        "kind": "sarif",
                        "path": str(FIXTURES / "sample.sarif.json"),
                        "sha256": "def456",
                        "parser": "sarif",
                        "summary": "security scan",
                        "trace_id": "trace-1",
                    },
                ],
                "trace_ids": ["trace-1"],
            },
        }
    )

    assert result["verdict"] == "pass"
    assert result["proofScore"] == {
        "score": 100,
        "band": "complete",
        "breakdown": {
            "completeness": 40,
            "validity": 35,
            "diversity": 15,
            "traceability": 10,
        },
    }
