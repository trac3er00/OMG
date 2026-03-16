from __future__ import annotations

from runtime.canonical_taxonomy import CANONICAL_PRESETS, RELEASE_CHANNELS, SUBSCRIPTION_TIERS
from runtime.policy_pack_loader import load_policy_pack, list_policy_packs, validate_policy_pack


def test_all_canonical_policy_packs_load_successfully() -> None:
    pack_ids = list_policy_packs()

    assert pack_ids == ["airgapped", "fintech", "locked-prod"]
    for pack_id in pack_ids:
        pack = load_policy_pack(pack_id)
        assert pack["id"] == pack_id


def test_policy_pack_ids_are_disjoint_from_presets_channels_and_tiers() -> None:
    pack_ids = set(list_policy_packs())

    assert pack_ids.isdisjoint(set(CANONICAL_PRESETS))
    assert pack_ids.isdisjoint(set(RELEASE_CHANNELS))
    assert pack_ids.isdisjoint(set(SUBSCRIPTION_TIERS))


def test_fintech_pack_has_required_controls() -> None:
    pack = load_policy_pack("fintech")

    assert pack["data_sharing"] == "restricted"
    assert pack["approval_threshold"] >= 2


def test_airgapped_pack_uses_airgapped_network_posture() -> None:
    pack = load_policy_pack("airgapped")

    assert pack["network_posture"] == "airgapped"


def test_locked_prod_pack_requires_high_approval_and_prohibits_sharing() -> None:
    pack = load_policy_pack("locked-prod")

    assert pack["approval_threshold"] >= 3
    assert pack["data_sharing"] == "prohibited"


def test_validate_policy_pack_rejects_reused_preset_id() -> None:
    invalid_pack: dict[str, object] = {
        "id": "safe",
        "description": "invalid pack id",
        "tool_restrictions": [],
        "network_posture": "restricted",
        "approval_threshold": 2,
        "protected_paths": [],
        "evidence_requirements": ["tests"],
        "data_sharing": "restricted",
    }

    errors = validate_policy_pack(invalid_pack)

    assert errors
    assert any("canonical preset" in error for error in errors)
