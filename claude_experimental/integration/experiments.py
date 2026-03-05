"""ExperimentTracker - A/B experiment tagging framework with variant assignment and metric comparison.

Design decisions:
- Shared SQLite DB with TelemetryCollector (.omg/state/telemetry.db)
- Connection-per-invocation (hooks are short-lived subprocesses, no pooling)
- WAL mode for concurrent multi-session access
- Deterministic variant assignment via hash-based default, random fallback
- Feature-gated via ADVANCED_INTEGRATION flag
- Schema versioning from day one
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
from datetime import datetime, timezone
from typing import cast

SCHEMA_VERSION = 1


def _default_db_path() -> str:
    """Return default experiments DB path (shared with telemetry)."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return os.path.join(project_dir, ".omg", "state", "telemetry.db")


class ExperimentTracker:
    """A/B experiment tagging framework with variant assignment and metric comparison.

    Supports defining experiments with multiple variants, deterministically assigning
    subjects to variants, and collecting per-variant metrics for comparison.

    Usage:
        tracker = ExperimentTracker()
        exp_id = tracker.define_experiment("pool_size", ["small", "large"])
        variant = tracker.assign_variant(exp_id, "user_123")
        tracker.tag_metric(exp_id, variant, "latency_ms", 42.5)
        results = tracker.compare(exp_id)
    """

    def __init__(self, db_path: str | None = None):
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        self.db_path: str = db_path or _default_db_path()
        self._ensure_dir()
        self._shared_memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_memory_conn = sqlite3.connect("file::memory:?cache=shared", uri=True, check_same_thread=False)
            self._shared_memory_conn.row_factory = sqlite3.Row
            self._init_schema(self._shared_memory_conn)

    def _ensure_dir(self) -> None:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection and initialize the schema if needed."""
        if self.db_path == ":memory:":
            if self._shared_memory_conn is None:
                raise RuntimeError("Shared memory connection not initialized")
            return self._shared_memory_conn
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

            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                variants TEXT NOT NULL,
                assignment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS experiment_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                variant TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                recorded_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            );

            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_exp_id ON experiment_metrics(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_variant ON experiment_metrics(variant);
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_name ON experiment_metrics(metric_name);
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

    def define_experiment(
        self,
        name: str,
        variants: list[str],
        assignment: str = "random",
    ) -> str:
        """Define a new A/B experiment.

        Args:
            name: Experiment name (e.g. "pool_size").
            variants: List of variant names (e.g. ["small", "large"]).
            assignment: Assignment strategy - "random" or "hash" (default "random").

        Returns:
            Experiment ID (UUID-like string).
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        if not variants or len(variants) < 2:
            raise ValueError("Experiment must have at least 2 variants")

        if assignment not in ("random", "hash"):
            raise ValueError("Assignment must be 'random' or 'hash'")

        # Generate experiment ID from name + timestamp
        now = datetime.now(timezone.utc).isoformat()
        exp_id = hashlib.sha256(f"{name}:{now}".encode()).hexdigest()[:16]

        conn = self._connect()
        try:
            _ = conn.execute(
                "INSERT INTO experiments (id, name, variants, assignment, created_at, schema_version) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    exp_id,
                    name,
                    json.dumps(variants),
                    assignment,
                    now,
                    SCHEMA_VERSION,
                ),
            )
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

        return exp_id

    def assign_variant(self, experiment_id: str, subject_id: str) -> str:
        """Assign a subject to a variant in an experiment.

        Deterministic for hash-based assignment (same subject always gets same variant).
        Random for random-based assignment.

        Args:
            experiment_id: Experiment ID from define_experiment().
            subject_id: Subject identifier (e.g. user ID, session ID).

        Returns:
            Assigned variant name.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        conn = self._connect()
        try:
            row = cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT variants, assignment FROM experiments WHERE id = ?",
                    (experiment_id,),
                ).fetchone(),
            )
            if row is None:
                raise ValueError(f"Experiment not found: {experiment_id}")

            variants = json.loads(row["variants"])
            assignment = row["assignment"]

            if assignment == "hash":
                # Deterministic: hash subject_id to select variant
                hash_val = int(
                    hashlib.sha256(f"{experiment_id}:{subject_id}".encode()).hexdigest(),
                    16,
                )
                variant = variants[hash_val % len(variants)]
            else:
                # Random assignment
                variant = random.choice(variants)

            return variant
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def tag_metric(
        self,
        experiment_id: str,
        variant: str,
        metric_name: str,
        value: float,
    ) -> None:
        """Record a metric observation for a variant in an experiment.

        Args:
            experiment_id: Experiment ID from define_experiment().
            variant: Variant name.
            metric_name: Metric name (e.g. "latency_ms").
            value: Numeric value.
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            _ = conn.execute(
                "INSERT INTO experiment_metrics (experiment_id, variant, metric_name, value, recorded_at, schema_version) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    variant,
                    metric_name,
                    value,
                    now,
                    SCHEMA_VERSION,
                ),
            )
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def compare(self, experiment_id: str) -> dict[str, dict[str, object]]:
        """Compare metrics across variants in an experiment.

        Args:
            experiment_id: Experiment ID from define_experiment().

        Returns:
            Dict mapping variant name to summary dict with keys:
            - count: number of observations
            - mean: average value
            - min: minimum value
            - max: maximum value
        """
        from claude_experimental.integration import _require_enabled
        _require_enabled()

        conn = self._connect()
        try:
            rows = cast(
                list[sqlite3.Row],
                conn.execute(
                    """
                    SELECT variant,
                           COUNT(*) as cnt,
                           AVG(value) as avg_val,
                           MIN(value) as min_val,
                           MAX(value) as max_val
                    FROM experiment_metrics
                    WHERE experiment_id = ?
                    GROUP BY variant
                    ORDER BY variant
                    """,
                    (experiment_id,),
                ).fetchall(),
            )

            result: dict[str, dict[str, object]] = {}
            for row in rows:
                result[row["variant"]] = {
                    "count": row["cnt"],
                    "mean": row["avg_val"],
                    "min": row["min_val"],
                    "max": row["max_val"],
                }

            return result
        finally:
            if self.db_path != ":memory:":
                conn.close()
