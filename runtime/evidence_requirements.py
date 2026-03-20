"""Single-source evidence profile requirements registry."""
from __future__ import annotations

import json
from typing import Final

FULL_REQUIREMENTS: Final[list[str]] = [
    "tests",
    "lsp_clean",
    "build",
    "provenance",
    "trust_scores",
    "security_scan",
    "license_scan",
    "sbom",
    "trace_link",
    "artifact_contracts",
    "signed_lineage",
    "signed_model_card",
    "signed_checkpoint",
    "simulator-episode-evidence",
]

HARDENED_READINESS_REQUIREMENTS: Final[list[str]] = list(FULL_REQUIREMENTS)

EVIDENCE_REQUIREMENTS_BY_PROFILE: Final[dict[str, list[str]]] = {
    "code-change": [
        "tests",
        "lsp_clean",
        "build",
        "provenance",
        "trace_link",
    ],
    "docs-only": [
        "lsp_clean",
        "trace_link",
    ],
    "forge-run": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
        "artifact_contracts",
    ],
    "browser-flow": [
        "lsp_clean",
        "trace_link",
        "provenance",
    ],
    "forge-cybersecurity": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
        "artifact_contracts",
        "security_scan",
    ],
    "interop-diagnosis": [
        "lsp_clean",
        "trace_link",
        "provenance",
        "trust_scores",
    ],
    "install-validation": [
        "tests",
        "lsp_clean",
        "build",
        "provenance",
        "trace_link",
    ],
    "music-omr": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
        "artifact_contracts",
    ],
    "forge-vision": list(HARDENED_READINESS_REQUIREMENTS)
    + [
        "vision-artifacts",
        "drift-check",
    ],
    "health-flow": list(HARDENED_READINESS_REQUIREMENTS)
    + [
        "human-review",
        "audit-trail",
        "restricted-tools",
    ],
    "team-flow": list(HARDENED_READINESS_REQUIREMENTS)
    + [
        "human-review",
        "audit-trail",
        "restricted-tools",
    ],
    "transposition-flow": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
        "artifact_contracts",
        "benchmark-harness",
        "determinism-check",
        "signed_lineage",
        "signed_model_card",
        "signed_checkpoint",
    ],
    "buffet": list(FULL_REQUIREMENTS),
    "security-audit": list(FULL_REQUIREMENTS),
    "release": list(FULL_REQUIREMENTS),
    # NF4: Task completion certification lanes
    "lane-feature-ship": [
        "tests",
        "lsp_clean",
        "build",
        "provenance",
        "trace_link",
    ],
    "lane-bug-fix": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
    ],
    "lane-security-remediation": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
        "security_scan",
    ],
    "lane-migration-refactor": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
    ],
    "lane-regression-recovery": [
        "tests",
        "lsp_clean",
        "provenance",
        "trace_link",
    ],
}

# NF4: Certification lane metadata
CERTIFICATION_LANES: Final[dict[str, dict[str, str]]] = {
    "lane-feature-ship": {
        "label": "Feature Ship",
        "gate_type": "active-gated",
        "description": "Full feature delivery with tests, build, and PR",
    },
    "lane-bug-fix": {
        "label": "Bug Fix",
        "gate_type": "active-gated",
        "description": "Bug fix with regression test and root cause verification",
    },
    "lane-security-remediation": {
        "label": "Security Remediation",
        "gate_type": "active-gated",
        "description": "Security fix with scan, CVE reference, and verification",
    },
    "lane-migration-refactor": {
        "label": "Migration / Refactor",
        "gate_type": "active-advisory",
        "description": "Migration or refactor with before/after parity proof",
    },
    "lane-regression-recovery": {
        "label": "Regression Recovery",
        "gate_type": "active-advisory",
        "description": "Regression recovery with reproduced test and green suite",
    },
}


def normalize_profile(raw: str) -> str:
    """Normalize a profile name: strip whitespace and lowercase."""
    return raw.strip().lower()


def resolve_profile(evidence_profile: str | None) -> str | None:
    """Resolve a profile name to its canonical registry key.

    Returns ``None`` for empty / ``None`` input (caller should use
    ``FULL_REQUIREMENTS``).  Returns the canonical key for known profiles
    (exact match first, then normalized).  Raises ``ValueError`` with a
    machine-readable JSON message for unknown profiles.
    """
    if not evidence_profile or not evidence_profile.strip():
        return None

    # Exact match
    if evidence_profile in EVIDENCE_REQUIREMENTS_BY_PROFILE:
        return evidence_profile

    # Normalized match (strip + lowercase)
    normalized = normalize_profile(evidence_profile)
    for key in EVIDENCE_REQUIREMENTS_BY_PROFILE:
        if normalize_profile(key) == normalized:
            return key

    # Unknown — fail closed with machine-readable error
    raise ValueError(
        json.dumps(
            {"status": "error", "reason": "unknown_profile", "profile": evidence_profile}
        )
    )


def requirements_for_profile(evidence_profile: str | None) -> list[str]:
    """Return the evidence requirement list for *evidence_profile*.

    ``None`` / empty  → ``FULL_REQUIREMENTS``.
    Known profile     → profile-specific list.
    Unknown profile   → raises ``ValueError`` (machine-readable JSON).
    """
    canonical = resolve_profile(evidence_profile)
    if canonical is None:
        return list(FULL_REQUIREMENTS)
    return list(EVIDENCE_REQUIREMENTS_BY_PROFILE[canonical])
