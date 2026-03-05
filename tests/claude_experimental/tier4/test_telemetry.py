"""Tests for claude_experimental.integration.telemetry — TelemetryCollector."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.fixture
def collector(tmp_path):
    """TelemetryCollector with file-backed temp DB."""
    from claude_experimental.integration.telemetry import TelemetryCollector

    return TelemetryCollector(str(tmp_path / "telemetry.db"))


@pytest.mark.experimental
class TestTelemetryRecording:
    """Counter, gauge, histogram round-trip tests."""

    def test_record_counter_and_query(self, collector):
        """record_counter() stores data queryable via query()."""
        collector.record_counter("api.requests", value=1)
        collector.record_counter("api.requests", value=1)
        collector.record_counter("api.requests", value=1)

        rows = collector.query("api.requests", since_minutes=60)
        assert len(rows) == 3
        for row in rows:
            assert row["metric_type"] == "counter"
            assert row["value"] == 1.0

    def test_record_gauge_and_query(self, collector):
        """record_gauge() stores point-in-time values."""
        collector.record_gauge("memory.usage_mb", 256.5)
        collector.record_gauge("memory.usage_mb", 512.0)

        rows = collector.query("memory.usage_mb", since_minutes=60)
        assert len(rows) == 2
        values = {row["value"] for row in rows}
        assert values == {256.5, 512.0}

    def test_record_histogram_and_query(self, collector):
        """record_histogram() stores distribution values."""
        for latency in [10.0, 20.0, 30.0, 40.0, 50.0]:
            collector.record_histogram("response.latency_ms", latency)

        rows = collector.query("response.latency_ms", metric_type="histogram")
        assert len(rows) == 5

    def test_counter_with_tags(self, collector):
        """Tags are stored and returned in query results."""
        collector.record_counter(
            "api.requests",
            value=1,
            tags={"endpoint": "/search", "method": "GET"},
        )

        rows = collector.query("api.requests")
        assert len(rows) == 1
        assert rows[0]["tags"]["endpoint"] == "/search"
        assert rows[0]["tags"]["method"] == "GET"


@pytest.mark.experimental
class TestTelemetryAggregation:
    """Aggregation tests."""

    def test_aggregate_sum(self, collector):
        """aggregate() returns correct sum for counter metrics."""
        for _ in range(10):
            collector.record_counter("my_metric", value=1)

        result = collector.aggregate("my_metric", period="minute")
        assert result["name"] == "my_metric"
        assert result["period"] == "minute"
        buckets = result["buckets"]
        assert len(buckets) >= 1
        total = sum(b["sum"] for b in buckets)
        assert total == 10.0

    def test_aggregate_min_max_avg(self, collector):
        """aggregate() returns correct min/max/avg."""
        collector.record_histogram("latency", 10.0)
        collector.record_histogram("latency", 20.0)
        collector.record_histogram("latency", 30.0)

        result = collector.aggregate("latency", period="hour")
        buckets = result["buckets"]
        assert len(buckets) == 1
        bucket = buckets[0]
        assert bucket["min"] == 10.0
        assert bucket["max"] == 30.0
        assert bucket["avg"] == 20.0
        assert bucket["count"] == 3


@pytest.mark.experimental
class TestTelemetryRotation:
    """Data rotation tests."""

    def test_rotate_old_data(self, tmp_path):
        """rotate_old_data() deletes metrics older than N days."""
        import sqlite3
        from datetime import datetime, timedelta, timezone

        from claude_experimental.integration.telemetry import TelemetryCollector

        db_path = str(tmp_path / "telemetry.db")
        tc = TelemetryCollector(db_path)

        # Insert recent data via API
        tc.record_counter("fresh_metric", value=1)

        # Manually insert old data (60 days ago)
        old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO metrics (name, metric_type, value, tags, recorded_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("old_metric", "counter", 1.0, "{}", old_time, 1),
        )
        conn.commit()
        conn.close()

        deleted = tc.rotate_old_data(days=30)
        assert deleted == 1

        # Fresh data should remain
        rows = tc.query("fresh_metric", since_minutes=60)
        assert len(rows) == 1


@pytest.mark.experimental
class TestTelemetryFeatureGate:
    """Feature flag gating."""

    def test_disabled_flag_raises(self, monkeypatch, tmp_path):
        """TelemetryCollector raises RuntimeError when flag is off."""
        from claude_experimental.integration.telemetry import TelemetryCollector

        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")

        with pytest.raises(RuntimeError, match="disabled"):
            TelemetryCollector(str(tmp_path / "telemetry.db"))
