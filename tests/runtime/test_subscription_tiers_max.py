"""Tests for the 'max' tier addition to subscription_tiers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from runtime.canonical_taxonomy import SUBSCRIPTION_TIERS
from runtime.subscription_tiers import TIER_REGISTRY, _normalize_tier_value


class TestMaxTierExists:
    def test_max_in_canonical_tiers(self):
        assert "max" in SUBSCRIPTION_TIERS

    def test_max_in_registry(self):
        assert "max" in TIER_REGISTRY

    def test_max_spec_values(self):
        spec = TIER_REGISTRY["max"]
        assert spec.budget_usd_per_session == 100.0
        assert spec.max_parallel_agents == 5
        assert "extended_context" in spec.features

    def test_tier_order_free_pro_max_team_enterprise(self):
        tiers = list(SUBSCRIPTION_TIERS)
        assert tiers.index("free") < tiers.index("pro")
        assert tiers.index("pro") < tiers.index("max")
        assert tiers.index("max") < tiers.index("team")
        assert tiers.index("team") < tiers.index("enterprise_tier")


class TestMaxTierAliases:
    def test_max_200_normalizes(self):
        assert _normalize_tier_value("max_200") == "max"

    def test_max_dash_200_normalizes(self):
        assert _normalize_tier_value("max-200") == "max"

    def test_max_direct(self):
        assert _normalize_tier_value("max") == "max"

    def test_existing_aliases_still_work(self):
        assert _normalize_tier_value("enterprise") == "enterprise_tier"
        assert _normalize_tier_value("enterprise-tier") == "enterprise_tier"


class TestRegistryConsistency:
    def test_registry_matches_taxonomy(self):
        assert set(TIER_REGISTRY.keys()) == set(SUBSCRIPTION_TIERS)

    def test_all_tiers_have_positive_budget(self):
        for name, spec in TIER_REGISTRY.items():
            assert spec.budget_usd_per_session > 0, f"{name} has non-positive budget"

    def test_all_tiers_have_positive_agents(self):
        for name, spec in TIER_REGISTRY.items():
            assert spec.max_parallel_agents >= 1, f"{name} has <1 agents"

    def test_max_agents_increase_with_tier(self):
        """Higher tiers should allow at least as many parallel agents as lower tiers."""
        tiers_ordered = list(SUBSCRIPTION_TIERS)
        agents = [TIER_REGISTRY[t].max_parallel_agents for t in tiers_ordered]
        for i in range(len(agents) - 1):
            assert agents[i] <= agents[i + 1], (
                f"{tiers_ordered[i]} agents ({agents[i]}) > "
                f"{tiers_ordered[i+1]} agents ({agents[i+1]})"
            )

    def test_max_budget_higher_than_pro(self):
        """Max plan ($100-200/mo) should have higher session budget than Pro ($20/mo)."""
        assert TIER_REGISTRY["max"].budget_usd_per_session > TIER_REGISTRY["pro"].budget_usd_per_session

    def test_enterprise_budget_highest(self):
        assert TIER_REGISTRY["enterprise_tier"].budget_usd_per_session >= max(
            spec.budget_usd_per_session for spec in TIER_REGISTRY.values()
        )
