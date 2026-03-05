"""DynamicPool — auto-scaling ThreadPoolExecutor wrapper.

Provides threshold-based worker pool scaling:
  - Scale up:   queue_depth > 2 × current_workers  → add workers (up to max_workers)
  - Scale down: queue_depth < 0.5 × current_workers for >30s → remove idle workers (down to min_workers)

Config defaults: min_workers=1, max_workers=100, scale_interval=10s.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


class DynamicPool:
    """Thread pool with automatic worker scaling based on queue depth.

    The pool monitors pending work every ``scale_interval`` seconds and adjusts
    the number of workers using simple threshold rules.  A daemon thread runs
    the monitor loop so it never blocks process exit.

    Args:
        min_workers: Floor for worker count (default 1).
        max_workers: Ceiling for worker count (default 100).
        scale_interval: Seconds between scaling checks (default 10).
    """

    def __init__(
        self,
        min_workers: int = 1,
        max_workers: int = 100,
        scale_interval: float = 10.0,
    ) -> None:
        if min_workers < 1:
            raise ValueError("min_workers must be >= 1")
        if max_workers < min_workers:
            raise ValueError("max_workers must be >= min_workers")
        if scale_interval <= 0:
            raise ValueError("scale_interval must be > 0")

        self._min_workers = min_workers
        self._max_workers = max_workers
        self._scale_interval = scale_interval

        self._current_workers = min_workers
        self._executor = ThreadPoolExecutor(max_workers=self._current_workers)

        # Tracking counters
        self._lock = threading.Lock()
        self._queued = 0
        self._active = 0
        self._completed = 0

        # Scale-down hysteresis: track when queue first dropped below threshold
        self._low_since: float | None = None
        self._SCALE_DOWN_HOLD_SECONDS = 30.0

        # Monitor thread
        self._shutdown_event = threading.Event()
        self._monitor = threading.Thread(
            target=self._monitor_loop,
            name="DynamicPool-monitor",
            daemon=True,
        )
        self._monitor.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        """Submit a callable for execution. Returns a ``concurrent.futures.Future``."""
        with self._lock:
            self._queued += 1

        future = self._executor.submit(self._wrapped, fn, *args, **kwargs)
        return future

    def pool_stats(self) -> dict[str, int]:
        """Return current pool statistics."""
        with self._lock:
            return {
                "active": self._active,
                "queued": self._queued,
                "completed": self._completed,
                "pool_size": self._current_workers,
            }

    def shutdown(self, wait: bool = True) -> None:
        """Stop the monitor thread and shut down the underlying executor."""
        self._shutdown_event.set()
        self._monitor.join(timeout=5.0)
        self._executor.shutdown(wait=wait)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wrapped(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Wrapper that tracks active/queued/completed counters around *fn*."""
        with self._lock:
            self._queued -= 1
            self._active += 1
        try:
            return fn(*args, **kwargs)
        finally:
            with self._lock:
                self._active -= 1
                self._completed += 1

    def _monitor_loop(self) -> None:
        """Background loop that periodically evaluates scaling decisions."""
        while not self._shutdown_event.is_set():
            self._shutdown_event.wait(timeout=self._scale_interval)
            if self._shutdown_event.is_set():
                break
            self._evaluate_scaling()

    def _evaluate_scaling(self) -> None:
        """Check queue depth against thresholds and resize pool if needed."""
        with self._lock:
            queue_depth = self._queued + self._active
            current = self._current_workers

        # --- Scale UP ---
        if queue_depth > 2 * current:
            new_size = min(queue_depth, self._max_workers)
            if new_size > current:
                self._resize(new_size)
                with self._lock:
                    self._low_since = None  # reset hysteresis
                return

        # --- Scale DOWN ---
        if queue_depth < 0.5 * current and current > self._min_workers:
            now = time.monotonic()
            should_shrink = False
            new_size = current
            with self._lock:
                if self._low_since is None:
                    self._low_since = now
                elif now - self._low_since >= self._SCALE_DOWN_HOLD_SECONDS:
                    new_size = max(self._min_workers, max(queue_depth, 1))
                    should_shrink = new_size < current
                    self._low_since = None
            if should_shrink:
                self._resize(new_size)
        else:
            with self._lock:
                self._low_since = None

    def _resize(self, new_size: int) -> None:
        """Replace the executor with one of *new_size* workers.

        In-flight futures continue on the old executor; new submissions go to
        the new one.  ``ThreadPoolExecutor`` does not support dynamic resizing,
        so we swap the instance.
        """
        old = self._executor
        self._executor = ThreadPoolExecutor(max_workers=new_size)
        with self._lock:
            self._current_workers = new_size
        # Shutdown old without blocking — in-flight work finishes naturally
        threading.Thread(
            target=old.shutdown,
            kwargs={"wait": True},
            name="DynamicPool-old-shutdown",
            daemon=True,
        ).start()
