from __future__ import annotations

from runtime.canonical_taxonomy import (
    CANONICAL_PRESETS,
    POLICY_PACK_IDS,
    RELEASE_CHANNELS,
    SUBSCRIPTION_TIERS,
)


def test_release_channels_are_canonical() -> None:
    assert RELEASE_CHANNELS == ("public", "enterprise")


def test_canonical_presets_are_stable() -> None:
    assert CANONICAL_PRESETS == ("safe", "balanced", "interop", "labs", "buffet", "production")


def test_subscription_tiers_do_not_overlap_channels_or_presets() -> None:
    tiers = set(SUBSCRIPTION_TIERS)
    assert tiers.isdisjoint(CANONICAL_PRESETS)
    assert tiers.isdisjoint(RELEASE_CHANNELS)


def test_policy_pack_ids_do_not_overlap_other_namespaces() -> None:
    policy_packs = set(POLICY_PACK_IDS)
    assert policy_packs.isdisjoint(CANONICAL_PRESETS)
    assert policy_packs.isdisjoint(RELEASE_CHANNELS)
    assert policy_packs.isdisjoint(SUBSCRIPTION_TIERS)
