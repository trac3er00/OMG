from __future__ import annotations

from typing import Final

from runtime.evidence_requirements import EVIDENCE_REQUIREMENTS_BY_PROFILE

CANONICAL_PARITY_HOSTS: Final[list[str]] = ["claude", "codex", "gemini", "kimi"]
COMPATIBILITY_ONLY_HOSTS: Final[list[str]] = ["opencode"]

DOMAIN_DEFAULTS: Final[dict[str, tuple[str, ...]]] = {
    "preflight_domain_packs": ("robotics", "vision", "algorithms", "health"),
    "all_domain_packs": ("robotics", "vision", "algorithms", "health", "cybersecurity"),
}

def _release_evidence_profile_labels() -> dict[str, str]:
    return {
        profile.replace("-", "_"): profile
        for profile in EVIDENCE_REQUIREMENTS_BY_PROFILE
    }


RELEASE_SURFACE_LABELS: Final[dict[str, dict[str, str]]] = {
    "evidence_profiles": {
        **_release_evidence_profile_labels(),
    },
    "routes": {
        "teams": "teams",
        "security_check": "security-check",
        "api_twin": "api-twin",
        "crazy": "crazy",
    },
}


def get_canonical_hosts() -> list[str]:
    return list(CANONICAL_PARITY_HOSTS)


def get_compat_hosts() -> list[str]:
    return list(COMPATIBILITY_ONLY_HOSTS)


def get_all_supported_hosts() -> list[str]:
    return [*CANONICAL_PARITY_HOSTS, *COMPATIBILITY_ONLY_HOSTS]


def is_canonical_parity_host(host: str) -> bool:
    return str(host).strip().lower() in CANONICAL_PARITY_HOSTS


def is_compat_only_host(host: str) -> bool:
    return str(host).strip().lower() in COMPATIBILITY_ONLY_HOSTS
