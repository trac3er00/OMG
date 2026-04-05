from __future__ import annotations


RELEASE_CHANNELS: tuple[str, ...] = ("public", "enterprise")
CANONICAL_PRESETS: tuple[str, ...] = ("safe", "balanced", "interop", "labs", "buffet", "production")
CANONICAL_PRESETS_SIMPLE: tuple[str, ...] = ("safe", "power", "dev")
SUBSCRIPTION_TIERS: tuple[str, ...] = ("free", "pro", "max", "team", "enterprise_tier")
POLICY_PACK_IDS: tuple[str, ...] = ("fintech", "airgapped", "locked-prod")

PRESET_HOOK_COUNT: dict[str, int] = {
    "safe": 15,
    "power": 35,
    "dev": 55,
}

PRESET_HOOK_MAPPING: dict[str, tuple[str, ...]] = {
    "safe": (
        "firewall", "secret-guard", "config-guard", "tdd-gate", "stop-gate",
        "session-start", "session-end-capture", "tool-ledger", "hashline-injector",
        "quality-runner", "budget_governor", "stop_dispatcher", "todo-state-tracker",
        "prompt-enhancer", "security_validators",
    ),
    "power": (
        "firewall", "secret-guard", "config-guard", "tdd-gate", "stop-gate",
        "session-start", "session-end-capture", "tool-ledger", "hashline-injector",
        "quality-runner", "budget_governor", "stop_dispatcher", "todo-state-tracker",
        "prompt-enhancer", "security_validators",
        "test-validator", "trust_review", "terms-guard", "test_generator_hook",
        "post-write", "query", "context_pressure", "pre-compact", "policy_engine",
        "secret_audit", "hashline-validator", "pre-tool-inject", "idle-detector",
        "post-tool-failure", "intentgate-keyword-detector", "shadow_manager",
        "credential_store", "fetch-rate-limits", "circuit-breaker", "branch_manager",
    ),
    "dev": (
        "firewall", "secret-guard", "config-guard", "tdd-gate", "stop-gate",
        "session-start", "session-end-capture", "tool-ledger", "hashline-injector",
        "quality-runner", "budget_governor", "stop_dispatcher", "todo-state-tracker",
        "prompt-enhancer", "security_validators",
        "test-validator", "trust_review", "terms-guard", "test_generator_hook",
        "post-write", "query", "context_pressure", "pre-compact", "policy_engine",
        "secret_audit", "hashline-validator", "pre-tool-inject", "idle-detector",
        "post-tool-failure", "intentgate-keyword-detector", "shadow_manager",
        "credential_store", "fetch-rate-limits", "circuit-breaker", "branch_manager",
        "state_migration", "instructions-loaded", "magic-keyword-router",
        "hashline-formatter-bridge", "policy_engine", "session-start",
        "compression_feedback", "learnings", "token_counter", "protected_context",
        "agent_registry", "analytics", "memory", "cost_ledger", "post_write",
    ),
}


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
