# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from __future__ import annotations

from runtime.steering_runtime import FailureEvent, STEERING_ACTIONS, SteeringRuntime


def test_no_failures_returns_retry() -> None:
    sr = SteeringRuntime()
    signal = sr.compute_steering()
    assert signal.action == "retry"
    assert signal.confidence > 0.5
    assert signal.failure_count == 0



def test_max_retries_exceeded_switches_approach() -> None:
    sr = SteeringRuntime(max_retries=2)
    for _ in range(3):
        sr.record_failure(FailureEvent("tool_error", "error", tool="pytest"))
    signal = sr.compute_steering(tool="pytest")
    assert signal.action == "switch_approach"



def test_critical_failure_escalates_model() -> None:
    sr = SteeringRuntime()
    sr.record_failure(FailureEvent("tool_error", "critical error", severity="critical"))
    signal = sr.compute_steering()
    assert signal.action == "escalate_model"



def test_budget_exceeded_reduces_scope() -> None:
    sr = SteeringRuntime()
    sr.record_failure(FailureEvent("budget_exceeded", "over budget"))
    signal = sr.compute_steering()
    assert signal.action == "reduce_scope"



def test_repeated_test_failures_add_context() -> None:
    sr = SteeringRuntime()
    sr.record_failure(FailureEvent("test_failure", "tests failed"))
    sr.record_failure(FailureEvent("test_failure", "tests failed again"))
    signal = sr.compute_steering()
    assert signal.action == "add_context"



def test_steering_signal_fields() -> None:
    sr = SteeringRuntime()
    signal = sr.compute_steering()
    assert signal.action in STEERING_ACTIONS
    assert 0.0 <= signal.confidence <= 1.0
    assert isinstance(signal.reason, str)
    assert isinstance(signal.failure_count, int)



def test_failure_summary_structure() -> None:
    sr = SteeringRuntime()
    sr.record_failure(FailureEvent("test_failure", "failed"))
    summary = sr.get_failure_summary()
    assert "total_failures" in summary
    assert "by_type" in summary
    assert summary["total_failures"] == 1
