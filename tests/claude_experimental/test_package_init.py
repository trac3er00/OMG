"""Tests for the top-level claude_experimental package."""
from __future__ import annotations


def test_tier_availability_handles_unshipped_tiers():
    import claude_experimental

    assert claude_experimental.__version__ == "2.0.0b4"

    availability = claude_experimental.tier_availability()

    assert availability["parallel"] is False
    assert availability["integration"] is False
    assert availability["memory"] is False
    assert availability["patterns"] is False
