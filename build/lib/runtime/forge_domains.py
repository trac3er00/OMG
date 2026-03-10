from __future__ import annotations

from typing import Any


CANONICAL_DOMAINS: dict[str, dict[str, Any]] = {
    "vision": {
        "canonical_id": "vision",
        "aliases": ["vision-agent"],
        "display_label": "Vision Agent",
        "starter_template_id": "vision-agent",
    },
    "robotics": {
        "canonical_id": "robotics",
        "aliases": [],
        "display_label": "Robotics",
        "starter_template_id": "robotics",
    },
    "algorithms": {
        "canonical_id": "algorithms",
        "aliases": [],
        "display_label": "Algorithms",
        "starter_template_id": "algorithms",
    },
    "health": {
        "canonical_id": "health",
        "aliases": [],
        "display_label": "Health",
        "starter_template_id": "health",
    },
    "cybersecurity": {
        "canonical_id": "cybersecurity",
        "aliases": [],
        "display_label": "Cybersecurity",
        "starter_template_id": "cybersecurity",
    },
}

# Build reverse alias map: alias -> canonical_id
_ALIAS_MAP: dict[str, str] = {}
for _canonical_id, _entry in CANONICAL_DOMAINS.items():
    _ALIAS_MAP[_canonical_id] = _canonical_id
    for _alias in _entry["aliases"]:
        _ALIAS_MAP[_alias] = _canonical_id


def canonical_domain_for(name: str) -> str:
    """Resolve a domain name or alias to its canonical domain ID.

    Raises ValueError for unknown domains.
    """
    normalized = str(name or "").strip().lower()
    if normalized not in _ALIAS_MAP:
        raise ValueError(
            f"Unknown domain: {name!r}. Valid domains: {sorted(CANONICAL_DOMAINS.keys())}"
        )
    return _ALIAS_MAP[normalized]


def is_valid_domain(name: str) -> bool:
    """Return True if name is a canonical domain ID or a known alias."""
    normalized = str(name or "").strip().lower()
    return normalized in _ALIAS_MAP


def get_all_canonical_domains() -> list[str]:
    """Return list of all canonical domain IDs."""
    return list(CANONICAL_DOMAINS.keys())
