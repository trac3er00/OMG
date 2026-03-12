from __future__ import annotations

import pytest

from runtime.domain_packs import get_domain_pack_contract


def test_health_domain_pack_enforces_human_review():
    contract = get_domain_pack_contract("health")
    assert contract["name"] == "health"
    assert contract["required_approvals"] == ["human-review"]
    assert "audit-trail" in contract["required_evidence"]


def test_vision_domain_pack_shape():
    contract = get_domain_pack_contract("vision")
    assert contract["name"] == "vision"
    assert contract["required_approvals"] == []
    assert "dataset-provenance" in contract["required_evidence"]
    assert "drift-check" in contract["required_evidence"]
    assert "vision-artifacts" in contract["required_evidence"]
    assert "dataset-lineage" in contract["policy_modules"]
    assert "vision-regression" in contract["eval_hooks"]
    assert "incident-replay" in contract["replay_hooks"]


def test_robotics_domain_pack_shape():
    contract = get_domain_pack_contract("robotics")
    assert contract["name"] == "robotics"
    assert "actuation-approval" in contract["required_approvals"]
    assert "simulator-replay" in contract["required_evidence"]
    assert "kill-switch-check" in contract["required_evidence"]
    assert "safe-actuation" in contract["policy_modules"]
    assert "robotics-sim" in contract["eval_hooks"]
    assert "incident-replay" in contract["replay_hooks"]


def test_algorithms_domain_pack_shape():
    contract = get_domain_pack_contract("algorithms")
    assert contract["name"] == "algorithms"
    assert contract["required_approvals"] == []
    assert "benchmark-harness" in contract["required_evidence"]
    assert "determinism-check" in contract["required_evidence"]
    assert "benchmark-gate" in contract["policy_modules"]
    assert "algorithm-benchmarks" in contract["eval_hooks"]
    assert "incident-replay" in contract["replay_hooks"]


def test_cybersecurity_domain_pack_shape():
    contract = get_domain_pack_contract("cybersecurity")
    assert contract["name"] == "cybersecurity"
    assert contract["required_approvals"] == []
    assert "security-scan" in contract["required_evidence"]
    assert "threat-model" in contract["required_evidence"]
    assert "sarif-report" in contract["required_evidence"]
    assert "security-gate" in contract["policy_modules"]
    assert "threat-gate" in contract["policy_modules"]
    assert "security-regression" in contract["eval_hooks"]
    assert "incident-replay" in contract["replay_hooks"]


def test_unknown_domain_raises_key_error():
    with pytest.raises(KeyError):
        get_domain_pack_contract("space")


def test_get_domain_pack_contract_returns_copy():
    contract1 = get_domain_pack_contract("vision")
    contract1["name"] = "mutated"
    contract2 = get_domain_pack_contract("vision")
    assert contract2["name"] == "vision"
