from __future__ import annotations

from runtime.domain_packs import get_domain_pack_contract


def test_health_domain_pack_enforces_human_review():
    contract = get_domain_pack_contract("health")
    assert contract["name"] == "health"
    assert contract["required_approvals"] == ["human-review"]
    assert "audit-trail" in contract["required_evidence"]
