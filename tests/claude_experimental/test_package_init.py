"""Smoke tests for claude_experimental package skeleton."""
from __future__ import annotations
import sys
import os
import pytest

# Ensure project root is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.mark.experimental
class TestPackageImports:
    """Verify all 4 tier packages import correctly."""

    def test_root_package_importable(self):
        from claude_experimental import __version__
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_parallel_tier_importable(self):
        from claude_experimental import parallel
        assert hasattr(parallel, "is_available")
        assert hasattr(parallel, "_require_enabled")

    def test_memory_tier_importable(self):
        from claude_experimental import memory
        assert hasattr(memory, "is_available")
        assert hasattr(memory, "_require_enabled")

    def test_patterns_tier_importable(self):
        from claude_experimental import patterns
        assert hasattr(patterns, "is_available")
        assert hasattr(patterns, "_require_enabled")

    def test_integration_tier_importable(self):
        from claude_experimental import integration
        assert hasattr(integration, "is_available")
        assert hasattr(integration, "_require_enabled")


@pytest.mark.experimental
class TestFeatureFlagGating:
    """Verify feature flags default to disabled and can be toggled."""

    def test_all_tiers_disabled_by_default(self):
        from claude_experimental import tier_availability
        avail = tier_availability()
        for tier_name, available in avail.items():
            assert available is False, f"Tier '{tier_name}' should default to disabled"

    def test_disabled_tier_raises_runtime_error(self):
        from claude_experimental.parallel import _require_enabled
        with pytest.raises(RuntimeError, match="disabled"):
            _require_enabled()

    def test_enable_via_env_var(self, feature_flag_enabled):
        feature_flag_enabled("PARALLEL_DISPATCH")
        # After enabling via env var, import fresh copy via importlib
        import importlib
        import claude_experimental._flags as flags_mod
        # Test that get_feature_flag returns True with env var set
        result = flags_mod.get_feature_flag("PARALLEL_DISPATCH", default=False)
        assert result is True, "Feature flag should be True when env var is set"

    def test_version_string_format(self):
        from claude_experimental import __version__
        # Should be semver-like
        assert "." in __version__, f"Version '{__version__}' should be semver-like"


@pytest.mark.experimental
class TestTierAvailabilityDict:
    """Verify tier_availability() returns expected structure."""

    def test_returns_dict_with_all_tiers(self):
        from claude_experimental import tier_availability
        avail = tier_availability()
        assert isinstance(avail, dict)
        assert set(avail.keys()) == {"parallel", "memory", "patterns", "integration"}

    def test_values_are_booleans(self):
        from claude_experimental import tier_availability
        avail = tier_availability()
        for key, val in avail.items():
            assert isinstance(val, bool), f"tier_availability()['{key}'] must be bool, got {type(val)}"
