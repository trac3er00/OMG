"""Tests for claude_experimental.integration.experiments — ExperimentTracker."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.fixture
def tracker(tmp_path):
    """ExperimentTracker with file-backed temp DB."""
    from claude_experimental.integration.experiments import ExperimentTracker

    return ExperimentTracker(str(tmp_path / "telemetry.db"))


@pytest.mark.experimental
class TestExperimentDefinition:
    """Experiment definition and variant assignment tests."""

    def test_define_experiment_returns_id(self, tracker):
        """define_experiment() returns a 16-char hex experiment ID."""
        exp_id = tracker.define_experiment("pool_size", ["small", "large"])
        assert isinstance(exp_id, str)
        assert len(exp_id) == 16

    def test_define_requires_two_variants(self, tracker):
        """define_experiment() raises ValueError with fewer than 2 variants."""
        with pytest.raises(ValueError, match="at least 2 variants"):
            tracker.define_experiment("bad_exp", ["only_one"])

    def test_hash_assignment_is_deterministic(self, tracker):
        """Hash-based assignment returns same variant for same subject."""
        exp_id = tracker.define_experiment(
            "hash_test", ["control", "treatment"], assignment="hash"
        )
        v1 = tracker.assign_variant(exp_id, "user_123")
        v2 = tracker.assign_variant(exp_id, "user_123")
        assert v1 == v2
        assert v1 in ("control", "treatment")

    def test_random_assignment_returns_valid_variant(self, tracker):
        """Random assignment returns a variant from the defined list."""
        exp_id = tracker.define_experiment("rand_test", ["A", "B", "C"])
        for _ in range(20):
            variant = tracker.assign_variant(exp_id, f"subject_{_}")
            assert variant in ("A", "B", "C")


@pytest.mark.experimental
class TestExperimentMetrics:
    """Metric tagging and comparison tests."""

    def test_tag_metric_and_compare(self, tracker):
        """tag_metric() records values; compare() returns per-variant stats."""
        exp_id = tracker.define_experiment("latency_test", ["small", "large"])

        # Tag metrics for each variant
        tracker.tag_metric(exp_id, "small", "latency", 100.0)
        tracker.tag_metric(exp_id, "small", "latency", 120.0)
        tracker.tag_metric(exp_id, "large", "latency", 80.0)

        result = tracker.compare(exp_id)

        assert "small" in result
        assert "large" in result
        assert result["small"]["count"] == 2
        assert result["small"]["mean"] == 110.0
        assert result["small"]["min"] == 100.0
        assert result["small"]["max"] == 120.0
        assert result["large"]["count"] == 1
        assert result["large"]["mean"] == 80.0

    def test_compare_empty_experiment(self, tracker):
        """compare() returns empty dict when no metrics are recorded."""
        exp_id = tracker.define_experiment("empty", ["A", "B"])
        result = tracker.compare(exp_id)
        assert result == {}

    def test_compare_with_metric_name_filters_to_that_metric(self, tracker):
        exp_id = tracker.define_experiment("filter_test", ["small", "large"])
        tracker.tag_metric(exp_id, "small", "latency", 100.0)
        tracker.tag_metric(exp_id, "small", "latency", 120.0)
        tracker.tag_metric(exp_id, "small", "success", 1.0)
        tracker.tag_metric(exp_id, "small", "success", 0.0)

        result = tracker.compare(exp_id, metric_name="latency")
        assert result["small"]["count"] == 2
        assert result["small"]["mean"] == 110.0
        assert result["small"]["min"] == 100.0
        assert result["small"]["max"] == 120.0

    def test_compare_without_metric_name_unchanged(self, tracker):
        exp_id = tracker.define_experiment("compat_test", ["v1", "v2"])
        tracker.tag_metric(exp_id, "v1", "latency", 50.0)
        tracker.tag_metric(exp_id, "v1", "latency", 70.0)

        result = tracker.compare(exp_id)
        assert result["v1"]["count"] == 2
        assert result["v1"]["mean"] == 60.0


@pytest.mark.experimental
class TestExperimentFeatureGate:
    """Feature flag gating."""

    def test_disabled_flag_raises(self, monkeypatch, tmp_path):
        """ExperimentTracker raises RuntimeError when flag is off."""
        from claude_experimental.integration.experiments import ExperimentTracker

        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")

        with pytest.raises(RuntimeError, match="disabled"):
            ExperimentTracker(str(tmp_path / "telemetry.db"))
