from __future__ import annotations

import pytest

from runtime.dual_mode import (
    MODE_GOVERNED,
    MODE_INSTANT,
    evaluate,
    format_mode_message,
    get_governance_requirements,
)


def test_governed_mode_message_has_prefix():
    result = evaluate(complexity="complex")
    assert result.mode == MODE_GOVERNED
    msg = format_mode_message(result, "Running test suite")
    assert msg.startswith("[GOVERNED]")


def test_instant_mode_message_no_prefix():
    result = evaluate(complexity="trivial")
    assert result.mode == MODE_INSTANT
    msg = format_mode_message(result, "Running test suite")
    assert not msg.startswith("[GOVERNED]")
    assert "Running test suite" in msg


def test_governed_requirements_full_governance():
    result = evaluate(complexity="complex")
    reqs = get_governance_requirements(result)
    assert reqs["proof_required"] is True
    assert reqs["claim_judge_active"] is True
    assert reqs["gate_mode"] == "hard"


def test_instant_requirements_advisory_only():
    result = evaluate(complexity="trivial")
    reqs = get_governance_requirements(result)
    assert reqs["proof_required"] is False
    assert reqs["claim_judge_active"] is False
    assert reqs["gate_mode"] == "advisory"


def test_team_project_always_governed(tmp_path):
    policy_dir = tmp_path / ".omg"
    policy_dir.mkdir()
    (policy_dir / "policy.yaml").write_text(
        "team:\n  members: [dev1]\n  roles:\n    dev1: developer\n"
    )
    result = evaluate(complexity="trivial", project_dir=str(tmp_path))
    assert result.mode == MODE_GOVERNED
    assert "team_config" in result.reason


def test_complex_task_governance_requirements():
    result = evaluate(complexity="critical")
    reqs = get_governance_requirements(result)
    assert reqs["gate_mode"] == "hard"
    assert "Governed" in reqs["note"]
