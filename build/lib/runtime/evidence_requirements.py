"""Single-source evidence profile requirements registry."""
from __future__ import annotations

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
}


def requirements_for_profile(evidence_profile: str | None) -> list[str]:
    if not evidence_profile:
        return list(FULL_REQUIREMENTS)
    requirements = EVIDENCE_REQUIREMENTS_BY_PROFILE.get(evidence_profile)
    if not requirements:
        return list(FULL_REQUIREMENTS)
    return list(requirements)
