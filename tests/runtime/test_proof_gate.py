from __future__ import annotations

from runtime.proof_gate import evaluate_proof_gate


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
                    "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "playwright-trace.zip"],
                    "trace_ids": ["trace-1"],
                }
            ],
            "proof_chain": {"status": "ok", "blockers": [], "trace_id": "trace-1"},
            "eval_output": {"trace_id": "trace-1", "status": "ok"},
        }
    )

    assert result["verdict"] == "pass"
    assert result["blockers"] == []
