from __future__ import annotations


RELEASE_CHANNELS: tuple[str, ...] = ("public", "enterprise")
CANONICAL_PRESETS: tuple[str, ...] = ("safe", "balanced", "interop", "labs", "buffet", "production")
SUBSCRIPTION_TIERS: tuple[str, ...] = ("free", "pro", "team", "enterprise_tier")
POLICY_PACK_IDS: tuple[str, ...] = ("fintech", "airgapped", "locked-prod")


def _assert_disjoint_namespaces() -> None:
    namespaces: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("RELEASE_CHANNELS", RELEASE_CHANNELS),
        ("CANONICAL_PRESETS", CANONICAL_PRESETS),
        ("SUBSCRIPTION_TIERS", SUBSCRIPTION_TIERS),
        ("POLICY_PACK_IDS", POLICY_PACK_IDS),
    )

    seen: dict[str, str] = {}
    for namespace, values in namespaces:
        for value in values:
            owner = seen.get(value)
            if owner is not None:
                raise ValueError(f"{value!r} is defined in both {owner} and {namespace}")
            seen[value] = namespace


_assert_disjoint_namespaces()
