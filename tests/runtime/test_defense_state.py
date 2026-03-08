from __future__ import annotations

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
