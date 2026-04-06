"""Failure-aware steering runtime for OMG.

Detects failure patterns in tool outputs and steering data.
Computes steering signals for re-routing around known failure modes.
Integrates with decision_ledger.py to learn from failures.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


FAILURE_TYPES = (
    "tool_error",
    "test_failure",
    "build_failure",
    "timeout",
    "budget_exceeded",
    "type_error",
)
STEERING_ACTIONS = (
    "retry",
    "escalate_model",
    "switch_approach",
    "reduce_scope",
    "add_context",
    "abort",
)


@dataclass
class FailureEvent:
    failure_type: str
    description: str
    tool: str = ""
    severity: str = "medium"  # low, medium, high, critical
    timestamp: float = 0.0
    context: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class SteeringSignal:
    action: str  # one of STEERING_ACTIONS
    confidence: float
    reason: str
    failure_count: int
    suggested_context: dict[str, object] = field(default_factory=dict)


class SteeringRuntime:
    """Tracks failure patterns and computes steering actions."""

    def __init__(self, max_retries: int = 3):
        self.max_retries: int = max_retries
        self._failures: list[FailureEvent] = []
        self._retry_counts: dict[str, int] = {}  # tool → count

    def record_failure(self, event: FailureEvent) -> None:
        self._failures.append(event)
        key = f"{event.failure_type}:{event.tool}"
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1

    def compute_steering(
        self,
        tool: str = "",
        context: dict[str, object] | None = None,
    ) -> SteeringSignal:
        """Compute steering action based on failure history.

        Returns a SteeringSignal with recommended action.
        """
        suggested_context = dict(context or {})

        if not self._failures:
            return SteeringSignal(
                action="retry",
                confidence=0.9,
                reason="no failures recorded",
                failure_count=0,
                suggested_context=suggested_context,
            )

        # Count recent failures for this tool
        recent_failures = [
            failure
            for failure in self._failures
            if time.time() - failure.timestamp < 300  # last 5 minutes
            and (not tool or failure.tool == tool)
        ]
        total_failures = len(self._failures)
        recent_count = len(recent_failures)

        # Check retry budget
        retry_key = f"tool_error:{tool}"
        retries = self._retry_counts.get(retry_key, 0)

        if retries >= self.max_retries:
            return SteeringSignal(
                action="switch_approach",
                confidence=0.85,
                reason=f"max retries ({self.max_retries}) exceeded for {tool or 'tool'}",
                failure_count=total_failures,
                suggested_context=suggested_context,
            )

        # Critical failures → escalate
        critical = [failure for failure in recent_failures if failure.severity == "critical"]
        if critical:
            return SteeringSignal(
                action="escalate_model",
                confidence=0.90,
                reason=f"critical failure detected: {critical[-1].failure_type}",
                failure_count=total_failures,
                suggested_context=suggested_context,
            )

        # Budget exceeded → reduce scope
        budget_failures = [
            failure
            for failure in recent_failures
            if failure.failure_type == "budget_exceeded"
        ]
        if budget_failures:
            return SteeringSignal(
                action="reduce_scope",
                confidence=0.80,
                reason="budget limit reached",
                failure_count=total_failures,
                suggested_context=suggested_context,
            )

        # Repeated build/test failures → add context
        persistent = [
            failure
            for failure in recent_failures
            if failure.failure_type in ("build_failure", "test_failure")
        ]
        if len(persistent) >= 2:
            return SteeringSignal(
                action="add_context",
                confidence=0.75,
                reason=f"{len(persistent)} build/test failures — need more context",
                failure_count=total_failures,
                suggested_context=suggested_context,
            )

        # Default: retry
        return SteeringSignal(
            action="retry",
            confidence=0.70,
            reason=f"retrying after {recent_count} recent failure(s)",
            failure_count=total_failures,
            suggested_context=suggested_context,
        )

    def get_failure_summary(self) -> dict[str, object]:
        return {
            "total_failures": len(self._failures),
            "by_type": {
                failure_type: sum(
                    1 for failure in self._failures if failure.failure_type == failure_type
                )
                for failure_type in FAILURE_TYPES
                if any(
                    failure.failure_type == failure_type for failure in self._failures
                )
            },
            "retry_counts": dict(self._retry_counts),
        }

    def clear_history(self) -> None:
        self._failures.clear()
        self._retry_counts.clear()
