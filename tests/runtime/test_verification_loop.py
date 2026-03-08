from __future__ import annotations

from runtime.verification_loop import (
    build_loop_policy,
    should_continue_loop,
    summarize_next_step,
)


def test_build_loop_policy_returns_expected_shape() -> None:
    policy = build_loop_policy(host="claude", max_iterations=3, timeout_minutes=10, read_only_default=True)

    assert policy == {
        "host": "claude",
        "max_iterations": 3,
        "timeout_minutes": 10,
        "read_only_default": True,
    }


def test_should_continue_loop_returns_true_within_budget() -> None:
    result = should_continue_loop({"iteration": 1, "max_iterations": 3, "status": "running"})

    assert result == {"continue": True, "reason": "within_budget"}


def test_should_continue_loop_returns_false_at_max_iterations() -> None:
    result = should_continue_loop({"iteration": 3, "max_iterations": 3, "status": "running"})

    assert result == {"continue": False, "reason": "max_iterations_reached"}


def test_should_continue_loop_returns_false_for_ok_status() -> None:
    result = should_continue_loop({"iteration": 1, "max_iterations": 3, "status": "ok"})

    assert result == {"continue": False, "reason": "status_ok"}


def test_summarize_next_step_returns_non_empty_next_action() -> None:
    result = summarize_next_step(
        {
            "status": "error",
            "blockers": ["missing trace ids in evidence"],
            "evidence_links": [".omg/evidence/run-1.json"],
        }
    )

    assert result["next_action"]
    assert result["evidence_links"] == [".omg/evidence/run-1.json"]
    assert result["blockers"] == ["missing trace ids in evidence"]
