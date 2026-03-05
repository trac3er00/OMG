"""Tests for claude_experimental.integration.autotuner — AutoTuner."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.fixture
def pool():
    """DynamicPool instance for testing."""
    from claude_experimental.parallel.scaling import DynamicPool

    p = DynamicPool(min_workers=1, max_workers=8)
    yield p
    p.shutdown(wait=False)


@pytest.fixture
def telemetry(tmp_path):
    """File-backed TelemetryCollector for round-trip P99 computation."""
    from claude_experimental.integration.telemetry import TelemetryCollector

    return TelemetryCollector(str(tmp_path / "telemetry.db"))


@pytest.mark.experimental
class TestAutoTunerScaleUp:
    """Scale-up tests based on P99 latency."""

    def test_high_latency_increases_workers(self, pool, telemetry):
        """P99 > 2× target triggers scale-up."""
        from claude_experimental.integration.autotuner import AutoTuner

        # Record high latency histogram values (> 2 × 5000ms = 10000ms)
        for _ in range(10):
            telemetry.record_histogram("task_duration_ms", 15000.0)

        tuner = AutoTuner(pool, telemetry, min_workers=1, max_workers=8, target_p99_ms=5000)
        result = tuner.tune_cycle()

        assert "max_workers" in result
        assert result["max_workers"] == 2  # scaled up from 1

    def test_normal_latency_no_change(self, pool, telemetry):
        """P99 within threshold produces no adjustment."""
        from claude_experimental.integration.autotuner import AutoTuner

        # Record normal latency (< 2 × 5000ms)
        for _ in range(10):
            telemetry.record_histogram("task_duration_ms", 3000.0)

        tuner = AutoTuner(pool, telemetry, min_workers=1, max_workers=8, target_p99_ms=5000)
        result = tuner.tune_cycle()

        assert result == {}  # No adjustment needed

    def test_scale_up_respects_max_workers(self, tmp_path):
        """Scale-up is capped at max_workers."""
        from claude_experimental.integration.autotuner import AutoTuner
        from claude_experimental.integration.telemetry import TelemetryCollector
        from claude_experimental.parallel.scaling import DynamicPool

        p = DynamicPool(min_workers=2, max_workers=3)
        tc = TelemetryCollector(str(tmp_path / "t.db"))

        try:
            for _ in range(10):
                tc.record_histogram("task_duration_ms", 20000.0)

            tuner = AutoTuner(p, tc, min_workers=2, max_workers=3, target_p99_ms=5000)
            result = tuner.tune_cycle()

            assert result["max_workers"] <= 3
        finally:
            p.shutdown(wait=False)


@pytest.mark.experimental
class TestAutoTunerParams:
    """Parameter query and validation tests."""

    def test_get_current_params(self, pool, telemetry):
        """get_current_params() returns expected structure."""
        from claude_experimental.integration.autotuner import AutoTuner

        tuner = AutoTuner(pool, telemetry, min_workers=1, max_workers=8, target_p99_ms=5000)
        params = tuner.get_current_params()

        assert params["min_workers"] == 1
        assert params["max_workers"] == 8
        assert params["target_p99_ms"] == 5000
        assert "current_workers" in params

    def test_no_data_no_adjustment(self, pool, telemetry):
        """When no telemetry data exists, tune_cycle() returns empty dict."""
        from claude_experimental.integration.autotuner import AutoTuner

        tuner = AutoTuner(pool, telemetry, target_p99_ms=5000)
        result = tuner.tune_cycle()
        assert result == {}

    def test_invalid_min_workers_raises(self, pool, telemetry):
        """min_workers < 1 raises ValueError."""
        from claude_experimental.integration.autotuner import AutoTuner

        with pytest.raises(ValueError, match="min_workers"):
            AutoTuner(pool, telemetry, min_workers=0)

    def test_invalid_target_p99_raises(self, pool, telemetry):
        """target_p99_ms <= 0 raises ValueError."""
        from claude_experimental.integration.autotuner import AutoTuner

        with pytest.raises(ValueError, match="target_p99_ms"):
            AutoTuner(pool, telemetry, target_p99_ms=0)


@pytest.mark.experimental
class TestAutoTunerFeatureGate:
    """Feature flag gating."""

    def test_disabled_flag_raises(self, monkeypatch, tmp_path):
        """AutoTuner raises RuntimeError when flag is off."""
        from claude_experimental.integration.autotuner import AutoTuner
        from claude_experimental.integration.telemetry import TelemetryCollector
        from claude_experimental.parallel.scaling import DynamicPool

        # Create with flag enabled first
        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")
        p = DynamicPool(min_workers=1, max_workers=4)
        tc = TelemetryCollector(str(tmp_path / "t.db"))

        # Now disable and try to create AutoTuner
        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")
        try:
            with pytest.raises(RuntimeError, match="disabled"):
                AutoTuner(p, tc)
        finally:
            p.shutdown(wait=False)
