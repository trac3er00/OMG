"""Optional domain pack contracts for high-risk verticals."""
from __future__ import annotations

from typing import Any

from runtime.canonical_surface import DOMAIN_DEFAULTS


DOMAIN_PACKS: dict[str, dict[str, Any]] = {
    "robotics": {
        "name": "robotics",
        "required_approvals": ["actuation-approval"],
        "required_evidence": ["simulator-replay", "kill-switch-check"],
        "policy_modules": ["safe-actuation", "simulator-gate"],
        "eval_hooks": ["robotics-sim"],
        "replay_hooks": ["incident-replay"],
    },
    "vision": {
        "name": "vision",
        "required_approvals": [],
        "required_evidence": ["dataset-provenance", "drift-check", "vision-artifacts"],
        "policy_modules": ["dataset-lineage", "drift-gate"],
        "eval_hooks": ["vision-regression"],
        "replay_hooks": ["incident-replay"],
    },
    "algorithms": {
        "name": "algorithms",
        "required_approvals": [],
        "required_evidence": ["benchmark-harness", "determinism-check"],
        "policy_modules": ["benchmark-gate", "determinism-gate"],
        "eval_hooks": ["algorithm-benchmarks"],
        "replay_hooks": ["incident-replay"],
    },
    "health": {
        "name": "health",
        "required_approvals": ["human-review"],
        "required_evidence": ["audit-trail", "restricted-tools", "provenance"],
        "policy_modules": ["human-review", "privacy-gate"],
        "eval_hooks": ["health-safety"],
        "replay_hooks": ["incident-replay"],
    },
    "cybersecurity": {
        "name": "cybersecurity",
        "required_approvals": [],
        "required_evidence": ["security-scan", "threat-model", "sarif-report"],
        "policy_modules": ["security-gate", "threat-gate"],
        "eval_hooks": ["security-regression"],
        "replay_hooks": ["incident-replay"],
    },
}

if set(DOMAIN_PACKS) != set(DOMAIN_DEFAULTS["all_domain_packs"]):
    raise ValueError("domain pack definitions drifted from canonical defaults")


def get_domain_pack_contract(name: str) -> dict[str, Any]:
    if name not in DOMAIN_PACKS:
        raise KeyError(name)
    return dict(DOMAIN_PACKS[name])


def get_required_approvals(name: str) -> list[str]:
    contract = get_domain_pack_contract(name)
    raw = contract.get("required_approvals")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def get_required_evidence(name: str) -> list[str]:
    contract = get_domain_pack_contract(name)
    raw = contract.get("required_evidence")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]
