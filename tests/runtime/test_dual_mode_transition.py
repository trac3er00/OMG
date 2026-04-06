from __future__ import annotations

from importlib import import_module

dual_mode = import_module("runtime.dual_mode")
DualModeSession = dual_mode.DualModeSession
MODE_GOVERNED = dual_mode.MODE_GOVERNED
MODE_INSTANT = dual_mode.MODE_INSTANT


def test_simple_task_stays_instant():
    session = DualModeSession(initial_complexity="trivial")
    assert session.mode == MODE_INSTANT
    result = session.update(complexity="simple")
    assert result.mode == MODE_INSTANT
    assert session.mode == MODE_INSTANT
    assert len(session.get_transitions()) == 0


def test_complexity_escalation_triggers_transition():
    session = DualModeSession(initial_complexity="trivial")
    assert session.mode == MODE_INSTANT
    result = session.update(complexity="complex")
    assert result.mode == MODE_GOVERNED
    assert session.mode == MODE_GOVERNED
    transitions = session.get_transitions()
    assert len(transitions) >= 1
    assert transitions[-1].from_mode == MODE_INSTANT
    assert transitions[-1].to_mode == MODE_GOVERNED
    assert "escalation" in transitions[-1].trigger


def test_env_override_prevents_transition(monkeypatch):
    monkeypatch.setenv("OMG_MODE", "instant")
    session = DualModeSession(initial_complexity="trivial")
    result = session.update(complexity="critical")
    assert result.mode == MODE_INSTANT
    assert session.mode == MODE_INSTANT


def test_transition_message_present_after_escalation():
    session = DualModeSession(initial_complexity="trivial")
    session.update(complexity="complex")
    msg = session.get_transition_message()
    assert msg is not None
    assert "Governed" in msg


def test_multi_file_change_triggers_transition():
    session = DualModeSession(initial_complexity="trivial")
    result = session.update(task={"files": 10, "lines_changed": 100})
    assert result.mode == MODE_GOVERNED
    assert session.mode == MODE_GOVERNED
    transitions = session.get_transitions()
    assert any("multi_file" in t.trigger for t in transitions)


def test_security_sensitive_triggers_transition():
    session = DualModeSession(initial_complexity="trivial")
    result = session.update(task={"files": 1, "risk_indicators": ["security", "auth"]})
    assert result.mode == MODE_GOVERNED
    assert session.mode == MODE_GOVERNED
