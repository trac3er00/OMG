from __future__ import annotations

import importlib
from pathlib import Path

from runtime.runtime_profile import load_runtime_profile
from runtime.subagent_dispatcher import resolve_dispatch_workers

ElasticPool = importlib.import_module("runtime.elastic_agent").ElasticPool


def test_elastic_pool_trivial_complexity_uses_single_agent() -> None:
    pool = ElasticPool(max_workers=8)

    assert pool.compute_agent_count("trivial") == 1


def test_elastic_pool_simple_complexity_uses_two_agents() -> None:
    pool = ElasticPool(max_workers=8)

    assert pool.compute_agent_count("simple") == 2


def test_elastic_pool_complex_complexity_scales_to_five_or_more_agents() -> None:
    pool = ElasticPool(max_workers=8)

    count = pool.compute_agent_count("complex")

    assert 5 <= count <= 8


def test_elastic_pool_budget_remaining_pct_limits_agent_count() -> None:
    pool = ElasticPool(max_workers=8, budget_remaining_pct=10)

    assert pool.compute_agent_count("complex") <= 2


def test_elastic_pool_rate_limited_caps_agent_count() -> None:
    pool = ElasticPool(max_workers=8, rate_limited=True)

    assert pool.compute_agent_count("critical") <= 2


def test_elastic_pool_should_scale_down_when_active_exceeds_pending() -> None:
    pool = ElasticPool(max_workers=8)

    assert pool.should_scale_down(active_count=5, pending_tasks=2) is True


def test_elastic_pool_should_not_scale_down_when_pending_exceeds_active() -> None:
    pool = ElasticPool(max_workers=8)

    assert pool.should_scale_down(active_count=2, pending_tasks=5) is False


def test_elastic_pool_respects_max_workers_cap() -> None:
    pool = ElasticPool(max_workers=4)

    assert pool.compute_agent_count("critical") == 4


def test_elastic_pool_max_for_budget_matches_budget_bands() -> None:
    assert ElasticPool(max_workers=8, budget_remaining_pct=10).max_for_budget() == 2
    assert ElasticPool(max_workers=8, budget_remaining_pct=40).max_for_budget() == 4
    assert ElasticPool(max_workers=6, budget_remaining_pct=80).max_for_budget() == 6


def test_load_runtime_profile_supports_elastic_mode(tmp_path: Path) -> None:
    runtime_dir = tmp_path / ".omg"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runtime.yaml").write_text("profile: elastic\n", encoding="utf-8")

    profile = load_runtime_profile(str(tmp_path))

    assert profile["profile"] == "elastic"
    assert profile["max_workers"] is None
    assert profile["description"]


def test_resolve_dispatch_workers_uses_elastic_pool_for_complex_tasks(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / ".omg"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runtime.yaml").write_text("profile: elastic\n", encoding="utf-8")

    workers = resolve_dispatch_workers(
        str(tmp_path),
        task_text="Implement a complex multi-agent orchestration workflow",
    )

    assert 5 <= workers <= 8


def test_resolve_dispatch_workers_scales_down_when_loop_detected(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / ".omg"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runtime.yaml").write_text("profile: elastic\n", encoding="utf-8")

    workers = resolve_dispatch_workers(
        str(tmp_path),
        task_text="Implement a complex multi-agent orchestration workflow",
        call_history=[
            {"tool": "read", "args": {"path": "runtime/elastic_agent.py"}},
            {"tool": "read", "args": {"path": "runtime/elastic_agent.py"}},
            {"tool": "read", "args": {"path": "runtime/elastic_agent.py"}},
        ],
    )

    assert workers == 1
