"""Cross-tier graceful degradation framework.

Provides fallback behavior when experimental features are unavailable,
with three degradation strategies: transparent fallback, annotated fallback,
and circuit breaker with automatic recovery.

No feature flag gate — this is meta-management infrastructure, always available.
"""
from __future__ import annotations

import enum
import functools
import sys
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Degradation tiers
# ---------------------------------------------------------------------------


class DegradationTier(enum.Enum):
    """Strategy for handling feature failures."""

    TRANSPARENT_FALLBACK = "transparent_fallback"
    """On exception, return fallback_value silently."""

    ANNOTATED_FALLBACK = "annotated_fallback"
    """On exception, log to stderr and return fallback_value."""

    CIRCUIT_BREAKER = "circuit_breaker"
    """After 3 consecutive failures within 60s, auto-disable for 5 minutes."""


# ---------------------------------------------------------------------------
# Circuit breaker constants
# ---------------------------------------------------------------------------

_CB_FAILURE_THRESHOLD = 3
_CB_FAILURE_WINDOW = 60.0  # seconds — failures must be within this window
_CB_OPEN_DURATION = 300.0  # seconds — circuit stays open for 5 minutes


# ---------------------------------------------------------------------------
# GracefulDegradation
# ---------------------------------------------------------------------------


class GracefulDegradation:
    """Wraps function execution with tier-appropriate fallback behavior.

    Parameters
    ----------
    tier : DegradationTier
        The degradation strategy to use.
    fallback_value : Any
        Value returned when the wrapped function fails (or circuit is open).
    feature_name : str
        Human-readable name for logging (used in ANNOTATED_FALLBACK stderr).
    """

    def __init__(
        self,
        tier: DegradationTier = DegradationTier.ANNOTATED_FALLBACK,
        fallback_value: Any = None,
        feature_name: str = "unknown",
    ) -> None:
        self._tier = tier
        self._fallback_value = fallback_value
        self._feature_name = feature_name

        # Stats
        self._failures: int = 0
        self._successes: int = 0

        # Circuit breaker state
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0
        self._circuit_open_until: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* with degradation protection.

        Returns the result of *fn* on success, or *fallback_value* on failure
        (behavior depends on the configured tier).
        """
        # Circuit breaker: if circuit is open, return fallback immediately
        if self._tier is DegradationTier.CIRCUIT_BREAKER:
            now = time.monotonic()
            if self._circuit_open_until > 0 and now < self._circuit_open_until:
                # Circuit is open — skip fn entirely
                return self._fallback_value
            # If circuit was open but time has elapsed, auto-close
            if self._circuit_open_until > 0 and now >= self._circuit_open_until:
                self._circuit_open_until = 0.0
                self._consecutive_failures = 0

        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            return self._handle_failure(exc)
        else:
            self._handle_success()
            return result

    def get_stats(self) -> dict[str, Any]:
        """Return degradation statistics."""
        circuit_open = (
            self._circuit_open_until > 0
            and time.monotonic() < self._circuit_open_until
        )
        return {
            "failures": self._failures,
            "successes": self._successes,
            "circuit_open": circuit_open,
            "feature_name": self._feature_name,
        }

    def reset(self) -> None:
        """Reset circuit breaker state (does not reset stats counters)."""
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._circuit_open_until = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_failure(self, exc: Exception) -> Any:
        """Process a failure according to the configured tier."""
        self._failures += 1

        if self._tier is DegradationTier.TRANSPARENT_FALLBACK:
            # Completely silent — no output
            return self._fallback_value

        if self._tier is DegradationTier.ANNOTATED_FALLBACK:
            print(
                f"[OMG DEGRADED] {self._feature_name}: {exc}",
                file=sys.stderr,
            )
            return self._fallback_value

        if self._tier is DegradationTier.CIRCUIT_BREAKER:
            now = time.monotonic()

            # If last failure was outside the window, reset consecutive count
            if (
                self._last_failure_time > 0
                and (now - self._last_failure_time) > _CB_FAILURE_WINDOW
            ):
                self._consecutive_failures = 0

            self._consecutive_failures += 1
            self._last_failure_time = now

            # Trip the circuit after threshold consecutive failures
            if self._consecutive_failures >= _CB_FAILURE_THRESHOLD:
                self._circuit_open_until = now + _CB_OPEN_DURATION

            return self._fallback_value

        # Fallback for unknown tiers (should not happen)
        return self._fallback_value  # pragma: no cover

    def _handle_success(self) -> None:
        """Process a success — resets consecutive failure count."""
        self._successes += 1
        if self._tier is DegradationTier.CIRCUIT_BREAKER:
            self._consecutive_failures = 0


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def graceful_degrade(
    tier: DegradationTier,
    fallback_value: Any = None,
    feature_name: str = "",
) -> Callable[[F], F]:
    """Decorator that wraps a function with graceful degradation.

    Usage::

        @graceful_degrade(DegradationTier.ANNOTATED_FALLBACK, fallback_value=[], feature_name="search")
        def search(query: str) -> list[str]:
            ...
    """

    def decorator(fn: F) -> F:
        name = feature_name or fn.__qualname__
        dg = GracefulDegradation(tier=tier, fallback_value=fallback_value, feature_name=name)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return dg.execute(fn, *args, **kwargs)

        # Expose the GracefulDegradation instance for inspection/reset
        wrapper._degradation = dg  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
