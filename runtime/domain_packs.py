"""Optional domain pack contracts for high-risk verticals."""
from __future__ import annotations

from typing import Any


DOMAIN_PACKS: dict[str, dict[str, Any]] = {
    "robotics": {
        "name": "robotics",
        "required_approvals": ["actuation-approval"],
        "required_evidence": ["simulator-replay", "kill-switch-check"],
    },
    "vision": {
        "name": "vision",
        "required_approvals": [],
        "required_evidence": ["dataset-provenance", "drift-check"],
    },
    "algorithms": {
        "name": "algorithms",
        "required_approvals": [],
        "required_evidence": ["benchmark-harness", "determinism-check"],
    },
    "health": {
        "name": "health",
        "required_approvals": ["human-review"],
        "required_evidence": ["audit-trail", "restricted-tools", "provenance"],
    },
}


def get_domain_pack_contract(name: str) -> dict[str, Any]:
    if name not in DOMAIN_PACKS:
        raise KeyError(name)
    return dict(DOMAIN_PACKS[name])
