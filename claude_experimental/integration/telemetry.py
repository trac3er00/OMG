"""TelemetryCollector - Lightweight local-only metrics collection and aggregation.

Design decisions:
- WAL mode for concurrent multi-session access
- Connection-per-invocation (hooks are short-lived subprocesses, no pooling)
- Separate SQLite DB from memory store (.omg/state/telemetry.db)
- Privacy-first: only numeric metrics, no content capture
- Schema versioning from day one
- Feature-gated via ADVANCED_INTEGRATION flag
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import cast

SCHEMA_VERSION = 1

_VALID_METRIC_TYPES = frozenset({"counter", "gauge", "histogram"})


def _default_db_path() -> str:
    """Return default telemetry DB path."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return os.path.join(project_dir, ".omg", "state", "telemetry.db")


class TelemetryCollector:
    """Local-only metrics collection with SQLite storage.

    Supports counter, gauge, and histogram metric types with time-based
    querying, aggregation, and automatic rotation of old data.

    Usage:
        collector = TelemetryCollector()
        collector.record_counter("api.requests", tags={"endpoint": "/search"})
        collector.record_gauge("memory.usage_mb", 256.5)
        collector.record_histogram("response.latency_ms", 42.3)

        metrics = collector.query("api.requests", since_minutes=60)
        agg = collector.aggregate("api.requests", period="minute")
        deleted = collector.rotate_old_data(days=30)
    """

    def __init__(self, db_path: str | None = None):
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        self.db_path: str = db_path or _default_db_path()
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection and initialize the schema if needed."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._init_schema(conn)
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        """Create schema if not exists."""
        _ = conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;

            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                value REAL NOT NULL,
                tags TEXT NOT NULL DEFAULT '{}',
                recorded_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
            CREATE INDEX IF NOT EXISTS idx_metrics_type ON metrics(metric_type);
            CREATE INDEX IF NOT EXISTS idx_metrics_recorded ON metrics(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_metrics_name_type ON metrics(name, metric_type);
        """)

        # Set schema version if not present
        row = cast(
            sqlite3.Row | None,
            conn.execute(
                "SELECT value FROM schema_info WHERE key='schema_version'"
            ).fetchone(),
        )
        if row is None:
            _ = conn.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        conn.commit()

    def _record(self, name: str, metric_type: str, value: float, tags: dict[str, str] | None) -> None:
        """Internal: insert a single metric row."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            _ = conn.execute(
                "INSERT INTO metrics (name, metric_type, value, tags, recorded_at, schema_version) VALUES (?, ?, ?, ?, ?, ?)",
                (name, metric_type, value, json.dumps(tags or {}), now, SCHEMA_VERSION),
            )
            conn.commit()
        finally:
            conn.close()

    def record_counter(self, name: str, value: float = 1, tags: dict[str, str] | None = None) -> None:
        """Record a counter metric (monotonically increasing value).

        Args:
            name: Metric name (e.g. "api.requests").
            value: Increment amount (default 1).
            tags: Optional key-value tags for filtering.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()
        self._record(name, "counter", value, tags)

    def record_gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a gauge metric (point-in-time value).

        Args:
            name: Metric name (e.g. "memory.usage_mb").
            value: Current value.
            tags: Optional key-value tags for filtering.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()
        self._record(name, "gauge", value, tags)

    def record_histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram metric (distribution of values).

        Args:
            name: Metric name (e.g. "response.latency_ms").
            value: Observed value.
            tags: Optional key-value tags for filtering.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()
        self._record(name, "histogram", value, tags)

    def query(
        self,
        name: str,
        metric_type: str | None = None,
        since_minutes: int = 60,
    ) -> list[dict[str, object]]:
        """Query metrics by name within a time window.

        Args:
            name: Metric name to query.
            metric_type: Optional filter by type (counter/gauge/histogram).
            since_minutes: Look back this many minutes (default 60).

        Returns:
            List of metric dicts with id, name, metric_type, value, tags, recorded_at.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()

        conn = self._connect()
        try:
            sql = "SELECT id, name, metric_type, value, tags, recorded_at FROM metrics WHERE name = ? AND recorded_at >= ?"
            params: list[object] = [name, cutoff]

            if metric_type is not None:
                sql += " AND metric_type = ?"
                params.append(metric_type)

            sql += " ORDER BY recorded_at DESC"

            rows = cast(list[sqlite3.Row], conn.execute(sql, params).fetchall())
            result: list[dict[str, object]] = []
            for r in rows:
                d = dict(r)
                # Parse tags JSON back to dict
                tags_raw = d.get("tags")
                if isinstance(tags_raw, str):
                    d["tags"] = json.loads(tags_raw)
                result.append(d)
            return result
        finally:
            conn.close()

    def aggregate(
        self,
        name: str,
        period: str = "minute",
    ) -> dict[str, object]:
        """Aggregate metrics by time period.

        Args:
            name: Metric name to aggregate.
            period: Aggregation period - 'minute', 'hour', or 'day'.

        Returns:
            Dict with keys: name, period, buckets (list of dicts with
            period_key, sum, count, min, max, avg).
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        # Map period to strftime format for SQLite grouping
        period_formats = {
            "minute": "%Y-%m-%dT%H:%M",
            "hour": "%Y-%m-%dT%H",
            "day": "%Y-%m-%d",
        }
        fmt = period_formats.get(period)
        if fmt is None:
            raise ValueError(f"Invalid period '{period}'. Must be 'minute', 'hour', or 'day'.")

        conn = self._connect()
        try:
            # Use substr to extract the period key from ISO8601 recorded_at
            key_len = len(fmt.replace("%Y", "2026").replace("%m", "03").replace("%d", "05")
                          .replace("%H", "12").replace("%M", "30"))
            sql = (
                "SELECT substr(recorded_at, 1, ?) as period_key, "
                "SUM(value) as total, COUNT(*) as cnt, "
                "MIN(value) as min_val, MAX(value) as max_val, AVG(value) as avg_val "
                "FROM metrics WHERE name = ? "
                "GROUP BY period_key ORDER BY period_key"
            )
            rows = cast(
                list[sqlite3.Row],
                conn.execute(sql, (key_len, name)).fetchall(),
            )

            buckets: list[dict[str, object]] = []
            for r in rows:
                buckets.append({
                    "period_key": r["period_key"],
                    "sum": r["total"],
                    "count": r["cnt"],
                    "min": r["min_val"],
                    "max": r["max_val"],
                    "avg": r["avg_val"],
                })

            return {
                "name": name,
                "period": period,
                "buckets": buckets,
            }
        finally:
            conn.close()

    def rotate_old_data(self, days: int = 30) -> int:
        """Delete metrics older than the specified number of days.

        Args:
            days: Delete data older than this many days (default 30).

        Returns:
            Number of rows deleted.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM metrics WHERE recorded_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
