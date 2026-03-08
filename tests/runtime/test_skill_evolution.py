from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import runtime.skill_evolution as skill_evolution  # pyright: ignore[reportMissingImports]


def test_propose_skill_returns_required_fields_and_persists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    proposal = skill_evolution.propose_skill(name="omg/example-skill", source="generated")

    assert proposal["status"] == "proposed"
    assert proposal["proposal_id"]
    assert proposal["name"] == "omg/example-skill"
    assert proposal["source"] == "generated"
    assert proposal["promoted"] is False

    artifact_path = tmp_path / str(proposal["artifact_path"])
    assert artifact_path.exists()
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["proposal_id"] == proposal["proposal_id"]
    assert persisted["status"] == "proposed"
    assert persisted["promoted"] is False


def test_promote_if_proven_returns_missing_for_unknown_proposal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    result = skill_evolution.promote_if_proven("missing-proposal")

    assert result["status"] == "missing"
    assert result["proposal_id"] == "missing-proposal"
    assert result["reason"] == "proposal_not_found"


def test_promote_if_proven_blocks_when_evaluation_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    proposal = skill_evolution.propose_skill(name="omg/example-skill", source="generated")
    result = skill_evolution.promote_if_proven(str(proposal["proposal_id"]))

    assert result["status"] == "blocked"
    assert result["reason"] == "evaluation_missing"


def test_evaluate_proposal_returns_shape_and_writes_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    proposal = skill_evolution.propose_skill(name="omg/example-skill", source="generated")

    def _fake_gate(_: dict[str, object]) -> dict[str, object]:
        return {
            "schema": "ProofGateResult",
            "verdict": "pass",
            "blockers": [],
            "evidence_summary": {"claim_count": 1},
        }

    monkeypatch.setattr(skill_evolution.proof_gate, "evaluate_proof_gate", _fake_gate)

    result = skill_evolution.evaluate_proposal(str(proposal["proposal_id"]), test_results={"claims": [{"claim_type": "tests_passed"}]})

    assert result["status"] == "evaluated"
    assert result["proposal_id"] == proposal["proposal_id"]
    assert result["promotable"] is True
    proof_gate_result = cast(dict[str, object], result["proof_gate_result"])
    assert proof_gate_result["verdict"] == "pass"

    eval_path = tmp_path / ".omg" / "state" / "skill-proposals" / f"{proposal['proposal_id']}-eval.json"
    assert eval_path.exists()
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    assert payload["status"] == "evaluated"
    assert payload["promotable"] is True
