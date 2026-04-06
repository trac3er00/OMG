# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

from runtime.steering_runtime import (
    FailureEvent,
    ReSteeringController,
    SteeringRuntime,
    SteeringSignal,
)


def test_escalate_signal_needs_resteering():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="escalate_model", confidence=0.9, reason="critical", failure_count=1
    )
    assert ctrl.should_resteer(signal) is True


def test_retry_signal_no_resteering():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="retry", confidence=0.7, reason="retrying", failure_count=1
    )
    assert ctrl.should_resteer(signal) is False


def test_plan_escalation():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="escalate_model", confidence=0.9, reason="critical", failure_count=1
    )
    plan = ctrl.plan_resteering(signal)
    assert plan.new_action == "retry_with_better_model"
    assert plan.model_preference is not None


def test_plan_switch_approach():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="switch_approach", confidence=0.85, reason="max retries", failure_count=3
    )
    plan = ctrl.plan_resteering(signal)
    assert plan.new_action == "alternative_implementation"
    assert len(plan.context_additions) > 0


def test_plan_add_context():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="add_context",
        confidence=0.75,
        reason="repeated failures",
        failure_count=2,
    )
    plan = ctrl.plan_resteering(signal)
    assert plan.new_action == "retry_with_context"
    assert len(plan.context_additions) > 0


def test_resteering_history_tracked():
    ctrl = ReSteeringController()
    signal = SteeringSignal(
        action="escalate_model", confidence=0.9, reason="critical", failure_count=1
    )
    ctrl.plan_resteering(signal)
    history = ctrl.get_resteering_history()
    assert len(history) == 1
    assert "original" in history[0]


def test_full_steering_flow():
    sr = SteeringRuntime(max_retries=1)
    ctrl = ReSteeringController(sr)
    sr.record_failure(FailureEvent("tool_error", "error", tool="build"))
    sr.record_failure(FailureEvent("tool_error", "error", tool="build"))
    signal = sr.compute_steering(tool="build")
    if ctrl.should_resteer(signal):
        plan = ctrl.plan_resteering(signal)
        assert plan is not None
        assert plan.new_action != ""
