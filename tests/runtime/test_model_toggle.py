# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import pytest

from runtime.model_toggle import MODES, get_mode, get_preferred_model, set_mode


@pytest.fixture(autouse=True)
def _reset_toggle():
    """Reset toggle to balanced before each test."""
    set_mode("balanced")
    yield
    set_mode("balanced")


def test_set_mode_fast_returns_dict():
    result = set_mode("fast")
    assert result["mode"] == "fast"
    assert "primary" in result
    assert "description" in result
    assert "cost_factor" in result


def test_get_preferred_model_fast_returns_cheap_model():
    set_mode("fast")
    model = get_preferred_model("medium")
    model_lower = model.lower()
    assert "haiku" in model_lower or "flash" in model_lower or "mini" in model_lower, (
        f"Fast mode should return a cheap model, got: {model}"
    )


def test_set_mode_quality_returns_dict():
    result = set_mode("quality")
    assert result["mode"] == "quality"
    assert "primary" in result


def test_get_preferred_model_quality_returns_opus():
    set_mode("quality")
    model = get_preferred_model("trivial")
    model_lower = model.lower()
    assert "opus" in model_lower, f"Quality mode should return opus, got: {model}"


def test_set_mode_balanced_returns_dict():
    result = set_mode("balanced")
    assert result["mode"] == "balanced"
    assert result["cost_factor"] == 1.0


def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="Invalid mode"):
        set_mode("turbo")


def test_get_mode_reflects_current():
    set_mode("fast")
    assert get_mode() == "fast"
    set_mode("quality")
    assert get_mode() == "quality"
    set_mode("balanced")
    assert get_mode() == "balanced"


def test_modes_dict_has_required_keys():
    for mode_name, mode_config in MODES.items():
        assert "primary" in mode_config, f"{mode_name} missing 'primary'"
        assert "description" in mode_config, f"{mode_name} missing 'description'"
        assert "cost_factor" in mode_config, f"{mode_name} missing 'cost_factor'"


def test_router_respects_fast_toggle():
    """ModelRouter should respect fast toggle and return cheap model."""
    from runtime.model_router import ModelRouter

    set_mode("fast")
    router = ModelRouter()
    decision = router.route(complexity="complex")
    model_lower = decision.model_id.lower()
    assert "haiku" in model_lower or "flash" in model_lower or "mini" in model_lower, (
        f"Router in fast mode should pick cheap model, got: {decision.model_id}"
    )


def test_router_respects_quality_toggle():
    """ModelRouter should respect quality toggle and return best model."""
    from runtime.model_router import ModelRouter

    set_mode("quality")
    router = ModelRouter()
    decision = router.route(complexity="trivial")
    model_lower = decision.model_id.lower()
    assert "opus" in model_lower, (
        f"Router in quality mode should pick opus, got: {decision.model_id}"
    )


def test_router_balanced_uses_complexity_routing():
    """In balanced mode, router should use complexity-based routing (not override)."""
    from runtime.model_router import ModelRouter

    set_mode("balanced")
    router = ModelRouter()
    decision = router.route(complexity="trivial")
    assert decision.model_id
