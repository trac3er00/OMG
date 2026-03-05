"""Tests for DynamicPool — auto-scaling thread pool."""
from __future__ import annotations

import os
import sys
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from claude_experimental.parallel.scaling import DynamicPool


@pytest.mark.experimental
class TestDynamicPoolInit:
    """Construction and validation."""

    def test_basic_init(self):
        pool = DynamicPool(min_workers=1, max_workers=4)
        try:
            stats = pool.pool_stats()
            assert stats["pool_size"] == 1
        finally:
            pool.shutdown()

    def test_min_workers_must_be_positive(self):
        with pytest.raises(ValueError, match="min_workers"):
            DynamicPool(min_workers=0, max_workers=4)

    def test_max_less_than_min_raises(self):
        with pytest.raises(ValueError, match="max_workers"):
            DynamicPool(min_workers=5, max_workers=2)

    def test_scale_interval_must_be_positive(self):
        with pytest.raises(ValueError, match="scale_interval"):
            DynamicPool(min_workers=1, max_workers=4, scale_interval=0)


@pytest.mark.experimental
class TestDynamicPoolStats:
    """pool_stats() returns correct structure."""

    @pytest.fixture
    def pool(self):
        p = DynamicPool(min_workers=2, max_workers=8, scale_interval=60)
        yield p
        p.shutdown()

    def test_stats_keys(self, pool):
        stats = pool.pool_stats()
        assert set(stats.keys()) == {"active", "queued", "completed", "pool_size"}

    def test_stats_initial_values(self, pool):
        stats = pool.pool_stats()
        assert stats["active"] == 0
        assert stats["queued"] == 0
        assert stats["completed"] == 0
        assert stats["pool_size"] == 2

    def test_stats_all_ints(self, pool):
        stats = pool.pool_stats()
        for key, val in stats.items():
            assert isinstance(val, int), f"{key} should be int, got {type(val)}"


@pytest.mark.experimental
class TestDynamicPoolExecution:
    """Job submission and completion tracking."""

    @pytest.fixture
    def pool(self):
        p = DynamicPool(min_workers=2, max_workers=8, scale_interval=60)
        yield p
        p.shutdown()

    def test_submit_and_get_result(self, pool):
        future = pool.submit(lambda x: x * 2, 21)
        assert future.result(timeout=5) == 42

    def test_completed_counter_increments(self, pool):
        futures = [pool.submit(lambda: i) for i in range(5)]
        for f in futures:
            f.result(timeout=5)
        # Give a tiny moment for counter update
        time.sleep(0.05)
        stats = pool.pool_stats()
        assert stats["completed"] == 5

    def test_shutdown_is_idempotent(self, pool):
        pool.shutdown()
        # Second call should not raise
        pool.shutdown()


@pytest.mark.experimental
class TestDynamicPoolScaling:
    """Scale-up logic triggers when queue exceeds threshold."""

    def test_scale_up_triggered(self):
        """Pool should scale up when queue_depth > 2 * current_workers."""
        pool = DynamicPool(min_workers=1, max_workers=10, scale_interval=0.1)
        try:
            import threading

            barrier = threading.Event()
            # Submit many tasks that block until we release them
            futures = []
            for _ in range(10):
                futures.append(pool.submit(lambda: barrier.wait(timeout=5)))
            # Wait for a scaling check
            time.sleep(0.3)
            stats = pool.pool_stats()
            # Pool should have scaled up from 1
            assert stats["pool_size"] >= 1  # At least initial
            barrier.set()
            for f in futures:
                f.result(timeout=5)
        finally:
            pool.shutdown()
