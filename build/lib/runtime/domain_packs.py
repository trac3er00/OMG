"""Optional domain pack contracts for high-risk verticals."""
from __future__ import annotations

from typing import Any


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
        "required_evidence": ["dataset-provenance", "drift-check"],
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
}


def get_domain_pack_contract(name: str) -> dict[str, Any]:
    if name not in DOMAIN_PACKS:
        raise KeyError(name)
    return dict(DOMAIN_PACKS[name])
