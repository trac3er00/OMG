from __future__ import annotations

import pytest
from pathlib import Path

from runtime.domain_packs import get_domain_pack_contract, list_packs, scaffold_project


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


def test_list_packs_returns_list(tmp_path):
    (tmp_path / "pack1").mkdir()
    (tmp_path / "pack1" / "pack.yaml").write_text(
        "name: pack1\ndescription: Test pack\ncategory: test\n"
    )
    packs = list_packs(packs_dir=tmp_path)
    assert len(packs) >= 1
    assert any(p["name"] == "pack1" for p in packs)


def test_list_packs_has_required_fields(tmp_path):
    (tmp_path / "mypk").mkdir()
    (tmp_path / "mypk" / "pack.yaml").write_text(
        "name: mypk\ndescription: d\ncategory: web\n"
    )
    packs = list_packs(packs_dir=tmp_path)
    for p in packs:
        assert "name" in p
        assert "description" in p
        assert "category" in p


def test_scaffold_project_creates_files(tmp_path):
    pack_dir = tmp_path / "domains" / "mypack"
    scaffold = pack_dir / "scaffold" / "src"
    scaffold.mkdir(parents=True)
    (scaffold / "index.ts").write_text("export default 'hello'")
    (pack_dir / "pack.yaml").write_text(
        "name: mypack\ndescription: test\ncategory: web\n"
    )
    target = tmp_path / "output"
    result = scaffold_project("mypack", target, packs_dir=tmp_path / "domains")
    assert result["success"] is True
    assert (target / "src" / "index.ts").exists()


def test_scaffold_project_installs_rules(tmp_path):
    pack_dir = tmp_path / "domains" / "withrulespack"
    rules = pack_dir / "rules"
    rules.mkdir(parents=True)
    (rules / "my-rule.md").write_text("# Rule")
    (pack_dir / "pack.yaml").write_text(
        "name: withrulespack\ndescription: t\ncategory: test\n"
    )
    target = tmp_path / "output"
    result = scaffold_project("withrulespack", target, packs_dir=tmp_path / "domains")
    assert "my-rule.md" in result["rules"]
    assert (target / ".omg" / "knowledge" / "rules" / "my-rule.md").exists()


def test_scaffold_nonexistent_pack_returns_error(tmp_path):
    result = scaffold_project("nonexistent", tmp_path / "out", packs_dir=tmp_path)
    assert result["success"] is False
    assert "error" in result


def test_list_empty_dir_returns_empty(tmp_path):
    packs = list_packs(packs_dir=tmp_path)
    assert packs == []
