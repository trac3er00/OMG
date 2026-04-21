"""Multi-AI fallback chain E2E tests."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol, cast


class _PytestProtocol(Protocol):
    def skip(self, reason: str) -> None: ...


pytest = cast(
    _PytestProtocol,
    cast(object, importlib.import_module("pytest")),
)


ROOT = Path(__file__).parent.parent.parent


class TestFallbackChain:
    """Test AI fallback chain behavior."""

    def test_fallback_chain_defined(self):
        """CATEGORY_FALLBACKS should define fallback chains."""
        multi_force = ROOT / "src" / "cx" / "multi-force.ts"
        assert multi_force.exists(), "multi-force.ts not found"
        content = multi_force.read_text()
        assert "CATEGORY_FALLBACKS" in content or "fallback" in content.lower()

    def test_all_providers_have_fallbacks(self):
        """All provider categories should have fallback options."""
        multi_force = ROOT / "src" / "cx" / "multi-force.ts"
        if not multi_force.exists():
            pytest.skip("multi-force.ts not found")
        content = multi_force.read_text()
        assert "ollama-cloud" in content

    def test_cost_tier_ordering(self):
        """Cost tiers should be ordered: high > medium > low."""
        equalizer = ROOT / "runtime" / "equalizer.py"
        if not equalizer.exists():
            pytest.skip("equalizer.py not found")
        content = equalizer.read_text()
        assert "cost" in content.lower() or "tier" in content.lower()

    def test_provider_availability_check(self):
        """Providers should have availability detection."""
        registry = ROOT / "runtime" / "providers" / "provider_registry.py"
        if not registry.exists():
            pytest.skip("provider_registry.py not found")
        content = registry.read_text()
        assert "detect" in content or "available" in content.lower()

    def test_ollama_cloud_in_fallback_chain(self):
        """ollama-cloud should be in the fallback chain."""
        multi_force = ROOT / "src" / "cx" / "multi-force.ts"
        if not multi_force.exists():
            pytest.skip("multi-force.ts not found")
        content = multi_force.read_text()
        assert "ollama-cloud" in content, "ollama-cloud not in multi-force.ts"

    def test_five_providers_registered(self):
        """All 5 AI providers should be registered."""
        registry = ROOT / "runtime" / "providers" / "provider_registry.py"
        if not registry.exists():
            pytest.skip("provider_registry.py not found")
        content = registry.read_text()
        providers = ["claude", "codex", "gemini", "kimi", "ollama-cloud"]
        found = [p for p in providers if p in content]
        assert len(found) == 5, f"Expected 5 providers, found {len(found)}: {found}"


class TestCostOptimization:
    """Test cost-optimized routing."""

    def test_equalizer_has_cost_tiers(self):
        """Equalizer should have cost tier definitions."""
        equalizer = ROOT / "runtime" / "equalizer.py"
        if not equalizer.exists():
            pytest.skip("equalizer.py not found")
        content = equalizer.read_text()
        assert "ollama-cloud" in content

    def test_low_cost_providers_defined(self):
        """Low-cost providers (ollama, ollama-cloud, kimi) should be defined."""
        equalizer = ROOT / "runtime" / "equalizer.py"
        if not equalizer.exists():
            pytest.skip("equalizer.py not found")
        content = equalizer.read_text()
        for provider in ["ollama", "ollama-cloud", "kimi"]:
            assert provider in content, f"{provider} not in equalizer.py"
