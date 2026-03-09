from __future__ import annotations

import json
from importlib import import_module

DefenseState = import_module("runtime.defense_state").DefenseState


def test_defense_state_update_returns_risk_level_and_actions(tmp_path) -> None:
    state = DefenseState(str(tmp_path)).update()
    assert state["risk_level"] == "low"
    assert state["actions"] == []


def test_defense_state_contamination_score_triggers_high_risk(tmp_path) -> None:
    state = DefenseState(str(tmp_path)).update(contamination_score=0.4)
    assert state["risk_level"] == "high"
    assert state["actions"] == ["warn", "flag"]


def test_defense_state_injection_hits_triggers_critical(tmp_path) -> None:
    state = DefenseState(str(tmp_path)).update(injection_hits=3)
    assert state["risk_level"] == "critical"
    assert state["actions"] == ["block", "quarantine"]


def test_defense_state_read_returns_safe_state_when_missing(tmp_path) -> None:
    state = DefenseState(str(tmp_path)).read()
    assert state["risk_level"] == "low"
    assert state["injection_hits"] == 0
    assert state["actions"] == []


def test_defense_state_computes_premature_fixer_for_clarification_sensitive_flow(tmp_path) -> None:
    (tmp_path / ".omg" / "shadow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "shadow" / "active-run").write_text("run-clarify\n", encoding="utf-8")
    intent_state = {
        "run_id": "run-clarify",
        "intent_class": "ambiguous_config",
        "requires_clarification": True,
        "confidence": 0.9,
    }
    intent_path = tmp_path / ".omg" / "state" / "intent_gate" / "run-clarify.json"
    intent_path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(json.dumps(intent_state), encoding="utf-8")

    state = DefenseState(str(tmp_path)).update(
        injection_hits=1,
        contamination_score=0.2,
        overthinking_score=0.6,
    )

    assert state["clarification_sensitive"] is True
    assert state["premature_fixer_score"] == 0.68


def test_defense_state_premature_fixer_score_is_zero_for_normal_flow(tmp_path) -> None:
    state = DefenseState(str(tmp_path)).update(
        injection_hits=2,
        contamination_score=0.6,
        overthinking_score=0.7,
    )
    assert state["clarification_sensitive"] is False
    assert state["premature_fixer_score"] == 0.0
