"""OAL v1 supply-chain verification with Warn-and-Run semantics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SupplyArtifact:
    id: str
    signer: str | None
    checksum: str | None
    permissions: list[str]
    static_scan: list[dict[str, Any]]
    risk_level: str = "low"


def _normalize(artifact: dict[str, Any]) -> SupplyArtifact:
    return SupplyArtifact(
        id=str(artifact.get("id", "unknown")),
        signer=artifact.get("signer"),
        checksum=artifact.get("checksum"),
        permissions=[str(p) for p in artifact.get("permissions", [])],
        static_scan=[f for f in artifact.get("static_scan", []) if isinstance(f, dict)],
        risk_level=str(artifact.get("risk_level", "low")).lower(),
    )


def verify_artifact(artifact: dict[str, Any], mode: str = "warn_and_run") -> dict[str, Any]:
    a = _normalize(artifact)
    reasons: list[str] = []
    controls: list[str] = []

    for finding in a.static_scan:
        sev = str(finding.get("severity", "")).lower()
        if sev == "critical":
            reasons.append("critical static scan finding")
            return {
                "action": "deny",
                "risk_level": "critical",
                "reason": "; ".join(reasons),
                "controls": ["block-execution"],
                "trusted": False,
            }

    perm_blob = " ".join(a.permissions).lower()
    if any(token in perm_blob for token in ["sudo", "rm -rf", "--privileged", "curl |", "wget |"]):
        return {
            "action": "deny",
            "risk_level": "critical",
            "reason": "critical permission profile",
            "controls": ["block-execution"],
            "trusted": False,
        }

    if not a.signer or not a.checksum:
        reasons.append("missing signer/checksum")
        controls.extend(["isolate-network", "read-only-fs", "manual-approval"])
        if mode == "warn_and_run":
            return {
                "action": "ask",
                "risk_level": "high",
                "reason": "; ".join(reasons),
                "controls": controls,
                "trusted": False,
            }
        return {
            "action": "deny",
            "risk_level": "high",
            "reason": "; ".join(reasons),
            "controls": ["block-execution"],
            "trusted": False,
        }

    if any(str(f.get("severity", "")).lower() == "high" for f in a.static_scan):
        return {
            "action": "ask",
            "risk_level": "high",
            "reason": "high severity findings present",
            "controls": ["manual-approval"],
            "trusted": False,
        }

    return {
        "action": "allow",
        "risk_level": a.risk_level if a.risk_level in {"low", "med", "high", "critical"} else "low",
        "reason": "artifact verified",
        "controls": [],
        "trusted": True,
    }
