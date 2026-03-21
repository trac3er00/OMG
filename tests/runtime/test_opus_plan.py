"""Tests for runtime.opus_plan — OpusPlan token optimization strategies.

Tests are organized around USER SCENARIOS:
- A Pro user expects OMG to conserve tokens and warn early
- A Max user expects full agent capabilities without restrictions
- A user with multiple providers expects the best tier to be detected
- Setup wizard needs correct capabilities to display to the user
- Budget governor needs correct thresholds to enforce limits
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = str(Path(__file__).resolve().parent.parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from runtime.opus_plan import (
    OPUS_PLAN_CONFIGS,
    get_model_routing,
    get_opus_plan,
    get_provider_plan,
    get_provider_plans,
    format_opus_plan_summary,
    format_provider_capabilities,
    resolve_effective_tier,
    should_prefer_escalate,
)


# ── Scenario: Pro user on a tight budget ────────────────────────────────────
# A Claude Pro user ($20/mo) expects OMG to conserve tokens aggressively.
# They should get fewer parallel agents, earlier warnings, and cheaper
# model routing so they don't burn through their session budget.

class TestProUserTokenConservation:
    """Pro user expects aggressive token conservation."""

    def test_opus_plan_is_active(self):
        config = get_opus_plan("pro")
        assert config.enabled is True

    def test_limited_to_2_parallel_agents(self):
        config = get_opus_plan("pro")
        assert config.max_parallel_agents == 2

    def test_warnings_fire_earlier_than_default(self):
        config = get_opus_plan("pro")
        # Default is 50%; Pro users should see warnings at 40%
        assert config.warning_threshold_pct < 50

    def test_budget_multiplier_reduces_effective_limit(self):
        config = get_opus_plan("pro")
        # Budget multiplier <1 means tighter effective spending limit
        assert config.budget_multiplier < 1.0
        assert config.budget_multiplier > 0

    def test_explore_tasks_use_cheap_model(self):
        assert get_model_routing("pro", "explore") == "haiku"
        assert get_model_routing("pro", "search") == "haiku"

    def test_implementation_uses_balanced_model(self):
        assert get_model_routing("pro", "implement") == "sonnet"

    def test_critical_decisions_still_get_opus(self):
        assert get_model_routing("pro", "security") == "opus"
        assert get_model_routing("pro", "architecture") == "opus"

    def test_prefers_escalate_over_ccg(self):
        # CCG (tri-model) is expensive; escalate is single-model
        assert should_prefer_escalate("pro") is True


# ── Scenario: Free tier user ────────────────────────────────────────────────
# Even more constrained than Pro. Single agent, aggressive compression.

class TestFreeUserMaxConservation:
    """Free user expects maximum conservation — single agent, earliest warnings."""

    def test_single_agent_only(self):
        config = get_opus_plan("free")
        assert config.max_parallel_agents == 1

    def test_aggressive_compression(self):
        config = get_opus_plan("free")
        assert config.context_compression == "aggressive"

    def test_earliest_warnings(self):
        config = get_opus_plan("free")
        assert config.warning_threshold_pct <= 30

    def test_tightest_budget(self):
        config = get_opus_plan("free")
        assert config.budget_multiplier <= 0.5


# ── Scenario: Max user expects full capabilities ────────────────────────────
# A Max user ($100-200/mo) with 1M context and high throughput expects no
# artificial restrictions — all agents, all models, no early warnings.

class TestMaxUserFullCapabilities:
    """Max user expects no restrictions."""

    def test_opus_plan_is_inactive(self):
        config = get_opus_plan("max")
        assert config.enabled is False

    def test_5_parallel_agents(self):
        config = get_opus_plan("max")
        assert config.max_parallel_agents == 5

    def test_no_context_compression(self):
        config = get_opus_plan("max")
        assert config.context_compression == "none"

    def test_standard_warning_threshold(self):
        config = get_opus_plan("max")
        assert config.warning_threshold_pct == 50

    def test_full_budget(self):
        config = get_opus_plan("max")
        assert config.budget_multiplier == 1.0

    def test_opus_for_implementation(self):
        assert get_model_routing("max", "implement") == "opus"

    def test_ccg_is_available(self):
        assert should_prefer_escalate("max") is False


@pytest.mark.parametrize("tier", ["team", "enterprise_tier"])
class TestHighTiersNoRestrictions:
    """Team and enterprise users also get no restrictions."""

    def test_opus_plan_inactive(self, tier):
        assert get_opus_plan(tier).enabled is False

    def test_no_escalate_preference(self, tier):
        assert should_prefer_escalate(tier) is False

    def test_full_budget_multiplier(self, tier):
        assert get_opus_plan(tier).budget_multiplier == 1.0


# ── Scenario: User with multiple providers ──────────────────────────────────
# A user has Claude Pro + Codex Team. OMG should detect the highest tier
# (team) so they get the best capabilities from their most capable provider.

class TestMultiProviderTierResolution:
    """User with multiple providers gets the highest effective tier."""

    def test_claude_pro_plus_codex_team_yields_team(self):
        assert resolve_effective_tier({"claude": "pro", "codex": "team"}) == "team"

    def test_claude_max_beats_codex_pro(self):
        assert resolve_effective_tier({"claude": "max", "codex": "pro"}) == "max"

    def test_single_provider(self):
        assert resolve_effective_tier({"claude": "pro"}) == "pro"

    def test_no_providers_defaults_to_free(self):
        assert resolve_effective_tier({}) == "free"

    def test_unknown_plans_ignored_gracefully(self):
        # User types garbage — shouldn't crash, should default to free
        assert resolve_effective_tier({"claude": "platinum_ultra"}) == "free"

    def test_mixed_known_and_unknown(self):
        # One valid, one invalid — valid one wins
        assert resolve_effective_tier({"claude": "max", "codex": "nonsense"}) == "max"


# ── Scenario: Unknown/invalid tier input ────────────────────────────────────
# User provides bad input during setup, or env var has a typo.
# System should never crash — always fall back to the safest config.

class TestEdgeCases:
    def test_unknown_tier_gets_safe_defaults(self):
        config = get_opus_plan("nonexistent_tier")
        assert config.enabled is True  # safe = active
        assert config.max_parallel_agents == 1

    def test_empty_string_tier(self):
        config = get_opus_plan("")
        assert config.enabled is True

    def test_none_like_tier(self):
        # resolve_effective_tier won't pass None, but get_opus_plan should handle it
        config = get_opus_plan("None")
        assert config.enabled is True  # defaults to free

    def test_unknown_task_type_gets_reasonable_default(self):
        # Constrained tier: unknown task → sonnet (middle ground)
        assert get_model_routing("pro", "some_new_task_type") == "sonnet"
        # Unconstrained tier: unknown task → opus
        assert get_model_routing("max", "some_new_task_type") == "opus"


# ── Scenario: Setup wizard needs provider info to display ────────────────────
# The /OMG:setup command shows users what each provider+plan offers.
# The data must be correct so users can make informed decisions.

class TestProviderCapabilitiesForSetup:
    def test_claude_pro_shows_200k_context(self):
        spec = get_provider_plan("claude", "pro")
        assert spec is not None
        assert spec.max_context_tokens == 200_000

    def test_claude_max_shows_1m_context(self):
        spec = get_provider_plan("claude", "max")
        assert spec is not None
        assert spec.max_context_tokens == 1_000_000

    def test_gemini_free_has_1m_context(self):
        """Gemini's free tier has 1M context — users should know this."""
        spec = get_provider_plan("gemini", "free")
        assert spec is not None
        assert spec.max_context_tokens == 1_000_000

    def test_codex_pro_supports_agents(self):
        spec = get_provider_plan("codex", "pro")
        assert spec is not None
        assert spec.supports_agents is True

    def test_claude_free_does_not_support_agents(self):
        spec = get_provider_plan("claude", "free")
        assert spec is not None
        assert spec.supports_agents is False

    @pytest.mark.parametrize("provider", ["claude", "codex", "gemini", "kimi"])
    def test_all_known_providers_have_specs(self, provider):
        plans = get_provider_plans(provider)
        assert len(plans) > 0, f"{provider} has no plan specs"

    def test_unknown_provider_returns_empty_not_error(self):
        assert get_provider_plans("unknown_ai") == {}

    def test_unknown_plan_returns_none_not_error(self):
        assert get_provider_plan("claude", "diamond") is None

    def test_format_capabilities_includes_key_info(self):
        text = format_provider_capabilities("claude", "pro")
        assert "claude" in text
        assert "200K" in text or "200" in text
        # Should show cost
        assert "$" in text


# ── Scenario: Budget governor reads OpusPlan config ─────────────────────────
# Budget governor reads settings.json for opus_plan config. The to_dict()
# output must serialize cleanly and contain all fields the governor expects.

class TestBudgetGovernorIntegration:
    def test_to_dict_serializes_to_valid_json(self):
        config = get_opus_plan("pro")
        d = config.to_dict()
        # Must round-trip through JSON
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        assert deserialized["enabled"] is True
        assert deserialized["budget_multiplier"] == 0.8

    def test_to_dict_has_all_governor_fields(self):
        config = get_opus_plan("pro")
        d = config.to_dict()
        required_keys = {
            "enabled", "max_parallel_agents", "context_compression",
            "warning_threshold_pct", "prefer_escalate_over_ccg", "budget_multiplier",
        }
        assert required_keys.issubset(d.keys())

    def test_threshold_computation_for_pro(self):
        """Budget governor computes thresholds from warning_threshold_pct."""
        config = get_opus_plan("pro")
        warn_pct = config.warning_threshold_pct  # 40
        thresholds = sorted({warn_pct, min(warn_pct + 30, 90), 95})
        assert thresholds == [40, 70, 95]

    def test_threshold_computation_for_free(self):
        config = get_opus_plan("free")
        warn_pct = config.warning_threshold_pct  # 30
        thresholds = sorted({warn_pct, min(warn_pct + 30, 90), 95})
        assert thresholds == [30, 60, 95]

    def test_effective_budget_with_multiplier(self):
        """Pro session limit of $20 * 0.8 multiplier = $16 effective."""
        from runtime.subscription_tiers import TIER_REGISTRY
        tier_budget = TIER_REGISTRY["pro"].budget_usd_per_session
        config = get_opus_plan("pro")
        effective = tier_budget * config.budget_multiplier
        assert effective == pytest.approx(16.0)


# ── Scenario: Format summary for user display ───────────────────────────────

class TestFormatSummary:
    def test_active_plan_clearly_says_active(self):
        summary = format_opus_plan_summary("pro")
        assert "ACTIVE" in summary

    def test_inactive_plan_clearly_says_inactive(self):
        summary = format_opus_plan_summary("max")
        assert "inactive" in summary

    def test_active_plan_shows_agent_limit(self):
        summary = format_opus_plan_summary("pro")
        assert "2" in summary  # max_parallel_agents

    def test_active_plan_shows_model_routing(self):
        summary = format_opus_plan_summary("free")
        assert "haiku" in summary


# ── Consistency: every canonical tier is covered ─────────────────────────────

class TestConfigCompleteness:
    def test_all_tiers_have_configs(self):
        from runtime.canonical_taxonomy import SUBSCRIPTION_TIERS
        assert set(OPUS_PLAN_CONFIGS.keys()) == set(SUBSCRIPTION_TIERS)

    def test_all_budget_multipliers_positive(self):
        for tier, config in OPUS_PLAN_CONFIGS.items():
            assert config.budget_multiplier > 0, f"{tier} has non-positive multiplier"

    @pytest.mark.parametrize("tier", list(OPUS_PLAN_CONFIGS.keys()))
    def test_warning_thresholds_in_valid_range(self, tier):
        config = OPUS_PLAN_CONFIGS[tier]
        assert 0 < config.warning_threshold_pct <= 100
