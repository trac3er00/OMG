"""AutoTuner — Automatic parameter tuning from telemetry signals.

Reads P99 latency and pool utilization from TelemetryCollector,
adjusts DynamicPool worker count using simple threshold-based rules:
  - Scale up:   P99 > 2× target_p99_ms → increase workers (up to max_workers)
  - Scale down: utilization < 30% for >30s → decrease workers (down to min_workers)

All tuning decisions are logged as ``autotuner_adjustment`` counter metrics.

Feature-gated via OMG_ADVANCED_INTEGRATION_ENABLED.
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from claude_experimental.integration.telemetry import TelemetryCollector
    from claude_experimental.parallel.scaling import DynamicPool


class AutoTuner:
    """Automatic parameter tuning from telemetry signals.

    Monitors P99 latency of ``task_duration_ms`` histogram metrics and
    pool utilization, adjusting DynamicPool worker count with simple
    threshold rules.  No Bayesian optimization — just reliable thresholds.

    Args:
        pool: DynamicPool instance to tune.
        telemetry: TelemetryCollector for reading metrics and logging decisions.
        min_workers: Minimum worker count floor (default 1).
        max_workers: Maximum worker count ceiling (default 8).
        target_p99_ms: Target P99 latency in milliseconds (default 5000).
    """

    _SUSTAINED_LOW_UTIL_SECONDS: float = 30.0
    _LOW_UTIL_THRESHOLD: float = 0.30  # 30%

    def __init__(
        self,
        pool: "DynamicPool",
        telemetry: "TelemetryCollector",
        min_workers: int = 1,
        max_workers: int = 8,
        target_p99_ms: float = 5000,
    ) -> None:
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        if min_workers < 1:
            raise ValueError("min_workers must be >= 1")
        if max_workers < min_workers:
            raise ValueError("max_workers must be >= min_workers")
        if target_p99_ms <= 0:
            raise ValueError("target_p99_ms must be > 0")

        self._pool = pool
        self._telemetry = telemetry
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._target_p99_ms = target_p99_ms

        # Hysteresis for sustained low-utilization scale-down
        self._low_util_since: float | None = None

    def tune_cycle(self) -> dict[str, int]:
        """Run one tuning cycle.

        Reads P99 latency and pool utilization, applies scaling rules,
        and returns a dict of parameter changes applied.

        Returns:
            ``{"max_workers": N}`` when an adjustment was made.
            Empty dict ``{}`` if no adjustment was needed.
        """
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        stats = self._pool.pool_stats()
        current_size: int = stats["pool_size"]

        # --- Rule 1: P99 > 2× target → scale UP ---
        p99 = self._compute_p99()
        if p99 is not None and p99 > 2 * self._target_p99_ms:
            new_size = min(current_size + 1, self._max_workers)
            if new_size > current_size:
                self._apply_resize(
                    new_size,
                    direction="up",
                    reason=f"p99={p99:.0f}ms > 2x target={self._target_p99_ms:.0f}ms",
                )
                self._low_util_since = None
                return {"max_workers": new_size}

        # --- Rule 2: utilization < 30% sustained → scale DOWN ---
        utilization = self._compute_utilization(stats)
        if utilization < self._LOW_UTIL_THRESHOLD and current_size > self._min_workers:
            now = time.monotonic()
            if self._low_util_since is None:
                self._low_util_since = now
            elif now - self._low_util_since >= self._SUSTAINED_LOW_UTIL_SECONDS:
                new_size = max(current_size - 1, self._min_workers)
                if new_size < current_size:
                    self._apply_resize(
                        new_size,
                        direction="down",
                        reason=(
                            f"utilization={utilization:.0%} < 30% "
                            f"for >{self._SUSTAINED_LOW_UTIL_SECONDS:.0f}s"
                        ),
                    )
                    self._low_util_since = None
                    return {"max_workers": new_size}
        else:
            # Reset hysteresis if utilization recovered
            self._low_util_since = None

        return {}

    def get_current_params(self) -> dict[str, object]:
        """Return current tunable parameters.

        Returns:
            Dict with ``min_workers``, ``max_workers``, ``current_workers``,
            and ``target_p99_ms``.
        """
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        stats = self._pool.pool_stats()
        return {
            "min_workers": self._min_workers,
            "max_workers": self._max_workers,
            "current_workers": stats["pool_size"],
            "target_p99_ms": self._target_p99_ms,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_p99(self) -> float | None:
        """Compute P99 latency from ``task_duration_ms`` histogram metrics.

        Queries the last 5 minutes of histogram data and computes the
        99th percentile from raw values.

        Returns:
            P99 latency in milliseconds, or ``None`` if no data available.
        """
        rows = self._telemetry.query(
            "task_duration_ms", metric_type="histogram", since_minutes=5
        )
        if not rows:
            return None

        values = sorted(cast(float, row["value"]) for row in rows)
        # 99th percentile: ceiling-based index
        idx = int(math.ceil(len(values) * 0.99)) - 1
        idx = max(0, min(idx, len(values) - 1))
        return values[idx]

    def _compute_utilization(self, stats: dict[str, int]) -> float:
        """Compute pool utilization as ``active / pool_size``."""
        pool_size = stats["pool_size"]
        if pool_size == 0:
            return 0.0
        return stats["active"] / pool_size

    def _apply_resize(self, new_size: int, *, direction: str, reason: str) -> None:
        """Resize the pool and log the tuning decision as telemetry."""
        self._pool._resize(new_size)
        self._telemetry.record_counter(
            "autotuner_adjustment",
            value=1,
            tags={"direction": direction, "reason": reason},
        )
