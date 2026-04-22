# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownMemberType=false

from __future__ import annotations

from pytest import MonkeyPatch

from runtime.router_selector import auto_select, select_target


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


def test_auto_select_returns_visual_fast_path_for_landing_page():
    selected = auto_select("landing page")

    assert selected["agent"] == "visual-engineering"
    assert selected["mode"] == "fast"
    assert selected["model"] == "claude-haiku-4-5"
    assert selected["auto_selected"] is True
    assert "complexity=" in str(selected["reasoning"])


def test_auto_select_respects_manual_overrides():
    selected = auto_select(
        "landing page",
        overrides={
            "agent": "librarian",
            "model": "custom-model",
            "mode": "quality",
        },
    )

    assert selected["agent"] == "librarian"
    assert selected["model"] == "custom-model"
    assert selected["mode"] == "quality"
    assert selected["auto_selected"] is True
    assert "manual override applied" in str(selected["reasoning"])


def test_auto_select_api_backend_routes_to_deep_agent():
    selected = auto_select("api backend")

    assert selected["agent"] == "deep"
    assert selected["auto_selected"] is True
    assert "gpt" in str(selected["model"]).lower() or selected["model"]
    assert "backend" in str(selected["reasoning"]).lower() or "api" in str(selected["reasoning"]).lower()
