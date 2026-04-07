# pyright: reportMissingImports=false
from __future__ import annotations

from runtime.failure_steering import FailureEvent, STEERING_ACTIONS, SteeringRuntime


def test_failure_steering_importable() -> None:
    sr = SteeringRuntime()
    signal = sr.compute_steering()
    assert signal.action in STEERING_ACTIONS
    assert signal.confidence >= 0.0


def test_circuit_opens_after_failures() -> None:
    sr = SteeringRuntime(max_retries=2)
    for _ in range(3):
        sr.record_failure(FailureEvent("tool_error", "repeated failure"))
    signal = sr.compute_steering()
    assert signal.action in ("switch_approach", "escalate_model", "abort")


def test_budget_fault_triggers_scope_reduction() -> None:
    sr = SteeringRuntime()
    sr.record_failure(FailureEvent("budget_exceeded", "over budget"))
    signal = sr.compute_steering()
    assert signal.action == "reduce_scope"
