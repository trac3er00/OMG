"""Performance-budget tests for hook latency and prompt packaging."""
from __future__ import annotations

from pathlib import Path

from runtime import team_router
from tests.perf import hook_latency as hook_latency_bench


def test_build_benchmark_payload_emits_budget_summary(tmp_path: Path):
    payload = hook_latency_bench.build_benchmark_payload(
        str(tmp_path),
        {
            "alpha.py": {
                "min_ms": 12.0,
                "avg_ms": 18.5,
                "max_ms": 21.0,
                "status": "ok",
                "error": None,
            },
            "slow.py": {
                "min_ms": 120.0,
                "avg_ms": 420.0,
                "max_ms": 510.0,
                "status": "ok",
                "error": None,
            },
        },
    )

    assert payload["schema"] == "OmgHookLatencyBaseline"
    assert payload["project_dir"] == str(tmp_path)
    assert payload["summary"]["hook_count"] == 2
    assert payload["summary"]["slowest_hook"] == "slow.py"
    assert payload["summary"]["over_budget"] == ["slow.py"]
    assert payload["budgets"]["max_avg_ms"] >= 200.0


def test_package_prompt_caps_output_and_reuses_registry_cache(monkeypatch, tmp_path: Path):
    load_calls: list[str] = []

    def fake_loader():
        load_calls.append("loaded")
        return {
            "backend-engineer": {
                "description": "Focused backend specialist",
                "model_version": "codex-cli",
            }
        }

    monkeypatch.setattr(team_router, "_load_agent_registry_snapshot", fake_loader, raising=False)
    monkeypatch.setattr(team_router, "_AGENT_REGISTRY_CACHE", None, raising=False)
    if hasattr(team_router, "_clear_agent_registry_cache"):
        team_router._clear_agent_registry_cache()

    huge_prompt = "optimize " * 1200
    packaged_one = team_router.package_prompt("backend-engineer", huge_prompt, str(tmp_path))
    packaged_two = team_router.package_prompt("backend-engineer", huge_prompt, str(tmp_path))

    assert len(packaged_one) <= team_router.PACKAGED_PROMPT_MAX_CHARS
    assert len(packaged_two) <= team_router.PACKAGED_PROMPT_MAX_CHARS
    assert "[truncated]" in packaged_one
    assert "Focused backend specialist" in packaged_one
    assert load_calls == ["loaded"]
