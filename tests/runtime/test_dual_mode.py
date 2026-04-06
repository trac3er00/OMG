from __future__ import annotations

import pytest

from runtime.dual_mode import MODE_GOVERNED, MODE_INSTANT, ModeResult, evaluate


def test_trivial_task_is_instant():
    """Trivial tasks should use Instant Mode."""
    result = evaluate(task={"files": 1, "lines_changed": 2, "type": "fix"})
    assert result.mode == MODE_INSTANT
    assert result.governance_active is False


def test_complex_task_is_governed():
    """Complex tasks should use Governed Mode."""
    result = evaluate(complexity="complex")
    assert result.mode == MODE_GOVERNED
    assert result.governance_active is True


def test_critical_task_is_governed():
    """Critical tasks should always use Governed Mode."""
    result = evaluate(complexity="critical")
    assert result.mode == MODE_GOVERNED


def test_env_override_forces_instant(monkeypatch):
    """OMG_MODE=instant forces instant even for complex tasks."""
    monkeypatch.setenv("OMG_MODE", "instant")
    result = evaluate(complexity="critical")
    assert result.mode == MODE_INSTANT
    assert "env_override" in result.reason


def test_team_config_forces_governed(tmp_path, monkeypatch):
    """Team config presence always forces Governed Mode."""
    monkeypatch.setenv("OMG_MODE", "instant")
    policy_dir = tmp_path / ".omg"
    policy_dir.mkdir()
    (policy_dir / "policy.yaml").write_text("team:\n  members: [dev1]\n")
    result = evaluate(complexity="trivial", project_dir=str(tmp_path))
    assert result.mode == MODE_GOVERNED
    assert "team_config" in result.reason


def test_mode_result_fields():
    """ModeResult should have all expected fields."""
    result = evaluate(complexity="simple")
    assert isinstance(result, ModeResult)
    assert result.mode in (MODE_INSTANT, MODE_GOVERNED)
    assert result.complexity
    assert result.reason
    assert isinstance(result.governance_active, bool)


def test_no_task_defaults_to_medium():
    """With no task or complexity, defaults to medium → governed."""
    result = evaluate()
    assert result.mode == MODE_GOVERNED
