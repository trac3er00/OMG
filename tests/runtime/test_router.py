from __future__ import annotations

from pytest import MonkeyPatch

from runtime.router_selector import select_target


def _tiers() -> dict[str, dict[str, str]]:
    return {
        "claude": {
            "light": "claude-light",
            "balanced": "claude-balanced",
            "heavy": "claude-heavy",
        },
        "gpt-5.4": {
            "light": "gpt-light",
            "balanced": "gpt-balanced",
            "heavy": "gpt-heavy",
        },
        "kimi": {
            "light": "kimi-light",
            "balanced": "kimi-balanced",
            "heavy": "kimi-heavy",
        },
    }


def test_simple_task_routes_to_lighter_model(monkeypatch: MonkeyPatch):
    monkeypatch.setenv("OMG_MULTI_MODEL_ROUTING_ENABLED", "1")

    selected = select_target(
        "fix typo",
        "quick pass",
        model_tiers=_tiers(),
    )

    assert selected["model_tier"] == "light"
    assert selected["model"] in {"claude-light", "gpt-light"}
    assert "model_recommendations" in selected
    recommendations = selected["model_recommendations"]
    assert isinstance(recommendations, dict)
    assert recommendations["gpt-5.4"] == "gpt-light"
    assert recommendations["kimi"] == "kimi-light"


def test_complex_task_routes_to_opus(monkeypatch: MonkeyPatch):
    monkeypatch.setenv("OMG_MULTI_MODEL_ROUTING_ENABLED", "1")

    selected = select_target(
        (
            "Design a full-stack architecture migration with numbered rollout phases, cross-service "
            "dependency analysis, security constraints, performance constraints, fallback rollback "
            "plans, and an end-to-end validation checklist for each subsystem."
        ),
        "deep architecture review",
        model_tiers=_tiers(),
    )

    assert selected["model_tier"] == "heavy"
    assert selected["model"] == "claude-heavy"
    complexity = selected["complexity"]
    assert isinstance(complexity, dict)
    assert complexity["category"] == "high"


def test_budget_constraint_forces_cheaper_model(monkeypatch: MonkeyPatch):
    monkeypatch.setenv("OMG_MULTI_MODEL_ROUTING_ENABLED", "1")

    selected = select_target(
        (
            "Design a full-stack architecture migration with numbered rollout phases, cross-service "
            "dependency analysis, security constraints, performance constraints, fallback rollback "
            "plans, and an end-to-end validation checklist for each subsystem."
        ),
        "deep architecture review",
        budget_remaining_ratio=0.1,
        model_tiers=_tiers(),
    )

    complexity = selected["complexity"]
    assert isinstance(complexity, dict)
    assert complexity["category"] == "high"
    assert selected["model_tier"] == "balanced"
    assert selected["model"] == "claude-balanced"
    assert selected["budget_remaining_ratio"] == 0.1
