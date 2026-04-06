# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

from runtime.model_registry import (
    ModelCapability,
    get_models_for,
    load_registry,
)


def test_load_registry_returns_models():
    registry = load_registry()
    assert len(registry) >= 5, "Registry should have at least 5 models"


def test_registry_has_all_5_providers():
    registry = load_registry()
    providers = {m.provider for m in registry.values()}
    assert "claude" in providers
    assert "openai" in providers


def test_get_models_for_low_budget():
    candidates = get_models_for(
        task_type="quick_tasks", budget="low", quality_floor="medium"
    )
    assert len(candidates) > 0
    for m in candidates:
        assert m.quality in ("medium", "high", "very_high")
    if len(candidates) > 1:
        assert candidates[0].cost_per_1k_tokens <= candidates[1].cost_per_1k_tokens


def test_get_models_for_high_quality():
    candidates = get_models_for(
        task_type="critical_tasks", budget="high", quality_floor="very_high"
    )
    for m in candidates:
        assert m.quality == "very_high"


def test_get_models_returns_sorted_by_cost():
    candidates = get_models_for(budget="unlimited", quality_floor="medium")
    assert all(isinstance(m, ModelCapability) for m in candidates)


def test_model_has_required_fields():
    registry = load_registry()
    for model in registry.values():
        assert model.model_id
        assert model.provider
        assert model.speed in ("fast", "medium", "slow")
        assert model.quality in ("low", "medium", "high", "very_high")
        assert model.cost_per_1k_tokens >= 0
        assert model.context_window > 0
