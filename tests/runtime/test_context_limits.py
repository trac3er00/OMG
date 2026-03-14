"""Tests for runtime.context_limits — canonical host/model context-limit registry.

Verifies the registry resolves correct limits for known 1M-class, 400k-class,
256k-class, and 200k-class host/model families, and that unknown models fall
back conservatively rather than silently inheriting stale 128k-era assumptions.
"""
from __future__ import annotations

import pytest

from runtime.context_limits import (
    ContextLimitEntry,
    compaction_trigger,
    get_model_limits,
    is_1m_class,
    supports_native_compaction,
    supports_preflight_counting,
)


# ---------------------------------------------------------------------------
# Fixtures — known model IDs by class
# ---------------------------------------------------------------------------

_1M_CLASS_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-4.1",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
]

_400K_CLASS_MODELS = [
    "gpt-5.2",
    "gpt-5",
]

_256K_CLASS_MODELS = [
    "kimi-k2.5",
    "kimi-k2-thinking",
]

_200K_CLASS_MODELS = [
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "o3",
    "o4-mini",
    "gemini-3-flash",
]

_128K_CLASS_MODELS = [
    "gpt-4o",
]


# ---------------------------------------------------------------------------
# Core acceptance test: known_model_limits
# ---------------------------------------------------------------------------

class TestKnownModelLimits:
    """QA scenario: known 1M-class and 256k-class models resolve correctly."""

    @pytest.mark.parametrize("model_id", _1M_CLASS_MODELS)
    def test_1m_class_models_exceed_900k(self, model_id: str) -> None:
        """1M-class models must report context_tokens > 900,000."""
        limits = get_model_limits(model_id)
        assert limits["context_tokens"] > 900_000, (
            f"{model_id} should have 1M-class window but got {limits['context_tokens']}"
        )
        assert limits["class_label"] == "1M-class"

    def test_claude_opus_4_6_exact(self) -> None:
        """claude-opus-4-6 must resolve to exactly 1,000,000 tokens."""
        limits = get_model_limits("claude-opus-4-6")
        assert limits["context_tokens"] == 1_000_000
        assert limits["class_label"] == "1M-class"
        assert limits["preflight_counting"] is True
        assert limits["native_compaction"] is True

    def test_gpt_5_4_exact(self) -> None:
        """gpt-5.4 must resolve to 1,050,000 tokens (not exactly 1M)."""
        limits = get_model_limits("gpt-5.4")
        assert limits["context_tokens"] == 1_050_000
        assert limits["class_label"] == "1M-class"
        assert limits["preflight_counting"] is True
        assert limits["native_compaction"] is True

    def test_gemini_3_1_pro_preview_exact(self) -> None:
        """gemini-3.1-pro-preview must resolve to 1,048,576 tokens."""
        limits = get_model_limits("gemini-3.1-pro-preview")
        assert limits["context_tokens"] == 1_048_576
        assert limits["class_label"] == "1M-class"
        assert limits["native_compaction"] is False  # Gemini has no native compaction

    @pytest.mark.parametrize("model_id", _256K_CLASS_MODELS)
    def test_kimi_k2_class(self, model_id: str) -> None:
        """Kimi K2.x models must resolve to 256k-class."""
        limits = get_model_limits(model_id)
        assert limits["context_tokens"] == 256_000
        assert limits["class_label"] == "256k-class"
        assert limits["preflight_counting"] is False  # No documented preflight endpoint

    @pytest.mark.parametrize("model_id", _400K_CLASS_MODELS)
    def test_400k_class_models(self, model_id: str) -> None:
        """GPT-5.2/5 models must resolve to 400k-class."""
        limits = get_model_limits(model_id)
        assert limits["context_tokens"] == 400_000
        assert limits["class_label"] == "400k-class"

    @pytest.mark.parametrize("model_id", _200K_CLASS_MODELS)
    def test_200k_class_models(self, model_id: str) -> None:
        """200k-class models must report context_tokens >= 200,000."""
        limits = get_model_limits(model_id)
        assert limits["context_tokens"] >= 200_000
        assert limits["class_label"] == "200k-class"


# ---------------------------------------------------------------------------
# QA scenario: unknown_model_fallback
# ---------------------------------------------------------------------------

class TestUnknownModelFallback:
    """QA scenario: unknown models use the documented fallback path, not stale 128k assumptions."""

    @pytest.mark.parametrize("unknown_model", [
        "unknown-model-xyz",
        "my-custom-llm",
        "",
        "future-model-v99",
        None,  # type: ignore[list-item]
    ])
    def test_unknown_model_fallback(self, unknown_model: str | None) -> None:
        """Unknown model IDs must fall back conservatively, not inherit a misleading limit."""
        limits = get_model_limits(str(unknown_model or ""))
        # The fallback must still be a valid ContextLimitEntry with a conservative limit
        assert limits["context_tokens"] > 0
        # Fallback is 128k — conservative but documented (not an arbitrary implicit choice)
        assert limits["context_tokens"] == 128_000, (
            f"Unknown model '{unknown_model}' should fall back to 128k, "
            f"got {limits['context_tokens']}"
        )
        assert limits["class_label"] == "128k-class"
        # Unknown models should NOT claim preflight counting
        assert limits["preflight_counting"] is False, (
            "Unknown model fallback should not claim preflight counting capability"
        )

    def test_fallback_not_inherited_from_1m_class(self) -> None:
        """Ensure a completely unknown model does NOT inherit 1M-class limits."""
        limits = get_model_limits("completely-unknown-provider/v1.0")
        assert not is_1m_class("completely-unknown-provider/v1.0")
        assert limits["context_tokens"] < 1_000_000, (
            "Unknown model must NOT silently inherit 1M-class limits"
        )


# ---------------------------------------------------------------------------
# Prefix matching
# ---------------------------------------------------------------------------

class TestPrefixMatching:
    """Verify prefix-based family lookup produces correct class assignments."""

    def test_claude_prefix_uses_conservative_fallback(self) -> None:
        """Unknown claude-* models fall back to 200k-class conservative entry."""
        limits = get_model_limits("claude-unknown-future-model")
        # Generic claude prefix → claude-haiku-4-5 (200k conservative)
        assert limits["context_tokens"] == 200_000
        assert limits["class_label"] == "200k-class"

    def test_gemini_prefix_uses_conservative_fallback(self) -> None:
        """Unknown gemini-* models fall back to 200k-class flash entry."""
        limits = get_model_limits("gemini-future-model")
        assert limits["context_tokens"] == 200_000
        assert limits["class_label"] == "200k-class"

    def test_kimi_prefix_matches_k2(self) -> None:
        """kimi-k2* models match via prefix lookup."""
        limits = get_model_limits("kimi-k2-turbo-preview")
        assert limits["context_tokens"] == 256_000
        assert limits["class_label"] == "256k-class"

    def test_gemini_3_1_prefix(self) -> None:
        """gemini-3.1-* prefix correctly resolves to 1M-class entry."""
        limits = get_model_limits("gemini-3.1-pro")
        assert limits["class_label"] == "1M-class"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Tests for is_1m_class, compaction_trigger, supports_* helpers."""

    def test_is_1m_class_true_for_opus(self) -> None:
        assert is_1m_class("claude-opus-4-6") is True

    def test_is_1m_class_false_for_kimi(self) -> None:
        assert is_1m_class("kimi-k2.5") is False

    def test_is_1m_class_false_for_unknown(self) -> None:
        assert is_1m_class("unknown-model") is False

    def test_compaction_trigger_1m_class(self) -> None:
        """1M-class hosts use higher compaction triggers than 200k-class."""
        trigger_1m = compaction_trigger("claude-opus-4-6")
        trigger_200k = compaction_trigger("claude-haiku-4-5")
        assert trigger_1m > trigger_200k, (
            "1M-class compaction trigger should be higher than 200k-class trigger"
        )

    def test_compaction_trigger_does_not_equal_context_window(self) -> None:
        """Compaction trigger must be well below the full context window (needs headroom)."""
        for model_id in ["claude-opus-4-6", "gpt-5.4", "gemini-3.1-pro-preview", "kimi-k2.5"]:
            limits = get_model_limits(model_id)
            trigger = compaction_trigger(model_id)
            # Trigger must leave at least 20% headroom for the compaction summary + future turns
            assert trigger < limits["context_tokens"] * 0.80, (
                f"{model_id}: compaction trigger {trigger} too close to "
                f"context window {limits['context_tokens']} — needs headroom for summary"
            )

    def test_supports_preflight_counting_claude(self) -> None:
        assert supports_preflight_counting("claude-sonnet-4-6") is True

    def test_supports_preflight_counting_kimi_false(self) -> None:
        assert supports_preflight_counting("kimi-k2.5") is False

    def test_supports_preflight_counting_unknown_false(self) -> None:
        assert supports_preflight_counting("unknown-model") is False

    def test_supports_native_compaction_openai(self) -> None:
        assert supports_native_compaction("gpt-5.4") is True

    def test_supports_native_compaction_gemini_false(self) -> None:
        assert supports_native_compaction("gemini-3.1-pro-preview") is False

    def test_supports_native_compaction_kimi_false(self) -> None:
        assert supports_native_compaction("kimi-k2.5") is False


# ---------------------------------------------------------------------------
# Structural integrity
# ---------------------------------------------------------------------------

class TestRegistryIntegrity:
    """Validate registry structure and required fields."""

    _REQUIRED_FIELDS = {
        "context_tokens",
        "output_reserve_tokens",
        "class_label",
        "preflight_counting",
        "native_compaction",
        "compaction_trigger_default",
        "notes",
    }

    def test_all_registry_entries_have_required_fields(self) -> None:
        """Every entry in _REGISTRY must have all required ContextLimitEntry fields."""
        from runtime.context_limits import _REGISTRY
        for model_id, entry in _REGISTRY.items():
            missing = self._REQUIRED_FIELDS - set(entry.keys())
            assert not missing, (
                f"Registry entry '{model_id}' missing fields: {missing}"
            )

    def test_fallback_has_all_required_fields(self) -> None:
        """The fallback entry must have all required fields."""
        from runtime.context_limits import _FALLBACK
        missing = self._REQUIRED_FIELDS - set(_FALLBACK.keys())
        assert not missing, f"_FALLBACK missing fields: {missing}"

    def test_all_context_windows_positive(self) -> None:
        """All context windows must be positive integers."""
        from runtime.context_limits import _REGISTRY, _FALLBACK
        for model_id, entry in {**_REGISTRY, "fallback": _FALLBACK}.items():
            assert entry["context_tokens"] > 0, (
                f"context_tokens must be positive for '{model_id}'"
            )

    def test_compaction_triggers_well_below_context(self) -> None:
        """Compaction triggers must leave at least 20% headroom in the context window."""
        from runtime.context_limits import _REGISTRY, _FALLBACK
        for model_id, entry in {**_REGISTRY, "fallback": _FALLBACK}.items():
            ratio = entry["compaction_trigger_default"] / entry["context_tokens"]
            assert ratio < 0.80, (
                f"Compaction trigger for '{model_id}' ({entry['compaction_trigger_default']}) "
                f"leaves less than 20%% headroom in context window ({entry['context_tokens']})"
            )
