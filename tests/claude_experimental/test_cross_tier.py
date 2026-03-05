from __future__ import annotations

from pathlib import Path
import time
from typing import cast

import pytest

pytestmark = pytest.mark.experimental


def test_tier_independence_memory_with_parallel_disabled(
    monkeypatch: pytest.MonkeyPatch,
    temp_db: str,
) -> None:
    monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")
    monkeypatch.delenv("OMG_PARALLEL_DISPATCH_ENABLED", raising=False)

    from claude_experimental.memory.store import MemoryStore
    from claude_experimental.parallel.executor import ParallelExecutor

    store = MemoryStore(db_path=temp_db, scope="project")
    memory_id = store.save("memory tier still works", memory_type="semantic")
    assert memory_id > 0

    with pytest.raises(RuntimeError, match="disabled"):
        _ = ParallelExecutor().submit("explore", "should fail while tier is disabled")


def test_graceful_degradation_wraps_tier_failure_with_fallback() -> None:
    from claude_experimental._degradation import DegradationTier, GracefulDegradation

    degradation = GracefulDegradation(
        tier=DegradationTier.CIRCUIT_BREAKER,
        fallback_value={"status": "fallback"},
        feature_name="parallel-dispatch",
    )

    def _failing_operation() -> dict[str, str]:
        raise RuntimeError("parallel tier unavailable")

    result = cast(dict[str, str] | None, degradation.execute(_failing_operation))
    assert result == {"status": "fallback"}


def test_lifecycle_health_contains_all_5_experimental_flags() -> None:
    from claude_experimental._lifecycle import FeatureFlagLifecycle

    lifecycle = FeatureFlagLifecycle()
    for flag_name in (
        "PARALLEL_DISPATCH",
        "EXPERIMENTAL_MEMORY",
        "PATTERN_INTELLIGENCE",
        "ADVANCED_INTEGRATION",
        "ULTRAWORKER",
    ):
        lifecycle.register(flag_name, status="alpha", since_version="2.0.0-beta.3")

    health = lifecycle.check_health()
    expected = {
        "PARALLEL_DISPATCH",
        "EXPERIMENTAL_MEMORY",
        "PATTERN_INTELLIGENCE",
        "ADVANCED_INTEGRATION",
        "ULTRAWORKER",
    }
    assert expected.issubset(set(health.keys()))


def test_memory_and_patterns_can_work_together(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMG_PATTERN_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    from claude_experimental.memory.api import remember
    from claude_experimental.memory.augmented_generation import MemoryAugmenter
    from claude_experimental.patterns.extractor import ASTExtractor

    source_file = tmp_path / "sample.py"
    _ = source_file.write_text("def analyze_code():\n    return 'ok'\n", encoding="utf-8")
    extracted = ASTExtractor().extract(str(source_file))
    assert any(pattern.name == "analyze_code" for pattern in extracted)

    memory_id = remember(
        "code analysis ast patterns function structures",
        importance=1.0,
        memory_type="semantic",
        scope="project",
    )
    assert memory_id > 0

    augmented = MemoryAugmenter().augment_prompt(
        "code analysis ast patterns",
        context_scope="project",
        max_memories=5,
    )
    assert "Relevant Context from Memory" in augmented
    assert "ast patterns" in augmented.lower()


def test_telemetry_collects_metrics_from_parallel_operations(
    monkeypatch: pytest.MonkeyPatch,
    temp_db: str,
) -> None:
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("OMG_PARALLEL_DISPATCH_ENABLED", "1")

    from claude_experimental.integration.telemetry import TelemetryCollector
    from claude_experimental.parallel.scaling import DynamicPool

    collector = TelemetryCollector(db_path=temp_db)
    pool = DynamicPool(min_workers=1, max_workers=4, scale_interval=60)

    try:
        delays_ms = [10.0, 20.0, 30.0]
        futures = [pool.submit(time.sleep, delay / 1000.0) for delay in delays_ms]

        for delay, future in zip(delays_ms, futures):
            future.result(timeout=3)
            collector.record_histogram("parallel.duration_ms", delay, tags={"source": "dynamic_pool"})
            collector.record_counter("parallel.completed", 1, tags={"source": "dynamic_pool"})

        histogram_agg = collector.aggregate("parallel.duration_ms", period="minute")
        assert histogram_agg["buckets"]

        histogram_rows = collector.query("parallel.duration_ms", metric_type="histogram", since_minutes=5)
        total_duration = sum(float(str(row.get("value", 0.0))) for row in histogram_rows)
        assert abs(total_duration - sum(delays_ms)) < 1e-6

        counters = collector.query("parallel.completed", metric_type="counter", since_minutes=5)
        assert len(counters) == 3
    finally:
        pool.shutdown()


def test_failure_learning_uses_memory_for_suggestions(
    monkeypatch: pytest.MonkeyPatch,
    temp_db: str,
) -> None:
    monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")

    from claude_experimental.memory.failure_learning import FailureLearner

    learner = FailureLearner(db_path=temp_db)
    failure_id = learner.record_failure(
        context="code analysis with AST patterns",
        error_type="RuntimeError",
        error_message="AST extraction timeout",
    )
    assert failure_id > 0

    suggestions = learner.suggest_fix(
        error_type="RuntimeError",
        context="AST patterns code analysis timeout",
        limit=3,
    )
    assert suggestions
    assert any(str(s.get("error_type", "")) == "RuntimeError" for s in suggestions)
    assert any("AST" in str(s.get("error_message", "")) for s in suggestions)
