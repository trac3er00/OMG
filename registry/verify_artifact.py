"""OMG v1 supply-chain verification with Warn-and-Run semantics."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class SupplyArtifact:
    id: str
    signer: str | None
    checksum: str | None
    attestation: dict[str, Any] | None
    signer_pubkey: str | None
    permissions: list[str]
    static_scan: list[dict[str, Any]]
    risk_level: str = "low"


_IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
_SLSA_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _key_id(signer_key: str) -> str:
    return hashlib.sha256(signer_key.encode("utf-8")).hexdigest()[:16]


def _subject_is_valid(subject: Any) -> bool:
    if not isinstance(subject, list) or not subject:
        return False
    first = subject[0]
    if not isinstance(first, dict):
        return False
    digest = first.get("digest")
    if not isinstance(digest, dict):
        return False
    sha256 = digest.get("sha256")
    if not isinstance(sha256, str):
        return False
    return len(sha256) == 64 and all(ch in "0123456789abcdef" for ch in sha256.lower())


def _statement_signing_payload(statement: dict[str, Any]) -> dict[str, Any]:
    return {
        "_type": statement.get("_type"),
        "predicateType": statement.get("predicateType"),
        "subject": statement.get("subject"),
        "predicate": statement.get("predicate"),
        "signer": statement.get("signer"),
        "issued_at": statement.get("issued_at"),
    }


def sign_artifact_statement(artifact_path: str, signer_key: str, subject_digest: str) -> dict[str, Any]:
    clean_path = str(artifact_path).strip()
    clean_digest = str(subject_digest).strip().lower()
    clean_key = str(signer_key)
    if not clean_path:
        raise ValueError("artifact_path_required")
    if not clean_key:
        raise ValueError("signer_key_required")
    if len(clean_digest) != 64 or any(ch not in "0123456789abcdef" for ch in clean_digest):
        raise ValueError("subject_digest_must_be_sha256_hex")

    key_id = _key_id(clean_key)
    issued_at = _utc_now()
    statement: dict[str, Any] = {
        "_type": _IN_TOTO_STATEMENT_TYPE,
        "predicateType": _SLSA_PREDICATE_TYPE,
        "subject": [
            {
                "name": clean_path,
                "digest": {"sha256": clean_digest},
            }
        ],
        "predicate": {
            "buildType": "https://omg.security/offline-attestation/v1",
            "metadata": {
                "signer": {
                    "keyid": key_id,
                    "algorithm": "hmac-sha256",
                    "mode": "local-offline",
                },
                "timestamp": issued_at,
            },
        },
        "signer": {
            "keyid": key_id,
            "algorithm": "hmac-sha256",
            "mode": "local-offline",
        },
        "issued_at": issued_at,
    }
    signature = hmac.new(clean_key.encode("utf-8"), _canonical_json(_statement_signing_payload(statement)), hashlib.sha256).digest()
    statement["signature"] = {
        "alg": "hmac-sha256",
        "keyid": key_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return statement


def verify_artifact_statement(statement: dict[str, Any], signer_pubkey: str) -> bool:
    if not isinstance(statement, dict):
        return False
    if str(statement.get("_type", "")) != _IN_TOTO_STATEMENT_TYPE:
        return False
    if str(statement.get("predicateType", "")) != _SLSA_PREDICATE_TYPE:
        return False
    if not _subject_is_valid(statement.get("subject")):
        return False

    signer = statement.get("signer")
    signature = statement.get("signature")
    if not isinstance(signer, dict) or not isinstance(signature, dict):
        return False

    key = str(signer_pubkey)
    if not key:
        return False
    expected_key_id = _key_id(key)
    if str(signer.get("keyid", "")) != expected_key_id:
        return False
    if str(signature.get("keyid", "")) != expected_key_id:
        return False
    if str(signature.get("alg", "")) != "hmac-sha256":
        return False

    try:
        actual_sig = base64.b64decode(str(signature.get("value", "")), validate=True)
    except Exception:
        return False

    expected_sig = hmac.new(
        key.encode("utf-8"),
        _canonical_json(_statement_signing_payload(statement)),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(actual_sig, expected_sig)


def _normalize(artifact: dict[str, Any]) -> SupplyArtifact:
    return SupplyArtifact(
        id=str(artifact.get("id", "unknown")),
        signer=artifact.get("signer"),
        checksum=artifact.get("checksum"),
        attestation=artifact.get("attestation") if isinstance(artifact.get("attestation"), dict) else None,
        signer_pubkey=artifact.get("signer_pubkey") if isinstance(artifact.get("signer_pubkey"), str) else None,
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

    if not a.attestation or not a.signer_pubkey:
        reasons.append("missing attestation statement")
        controls.extend(["isolate-network", "manual-approval"])
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

    if not verify_artifact_statement(a.attestation, a.signer_pubkey):
        reasons.append("invalid attestation statement")
        if mode == "warn_and_run":
            return {
                "action": "ask",
                "risk_level": "high",
                "reason": "; ".join(reasons),
                "controls": ["manual-approval", "forensic-review"],
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
