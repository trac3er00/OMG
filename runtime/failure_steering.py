"""Failure-aware steering runtime — canonical alias module.

This module re-exports all symbols from ``runtime.steering_runtime``,
which is the canonical implementation of Tasks 42-43 (failure-aware
circuit-breaker state machine and re-steering logic).

Import from either module — they are functionally identical.
"""

from __future__ import annotations

from runtime.steering_runtime import (  # noqa: F401
    FAILURE_TYPES,
    STEERING_ACTIONS,
    FailureEvent,
    ReSteeringController,
    ReSteeringPlan,
    SteeringRuntime,
    SteeringSignal,
)

__all__ = [
    "FAILURE_TYPES",
    "STEERING_ACTIONS",
    "FailureEvent",
    "ReSteeringController",
    "ReSteeringPlan",
    "SteeringRuntime",
    "SteeringSignal",
]
