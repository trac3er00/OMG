"""OMG v1 supply-chain verification with Warn-and-Run semantics."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
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
_TRUST_ROOT_PATH = Path(__file__).with_name("trusted_signers.json")
_DEFAULT_DEV_SIGNER_KEY_ID = "1f5fe64ec2f8c901"


def _load_ed25519_backend() -> tuple[Any, Any, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "cryptography backend unavailable; run OMG setup to provision the managed venv"
        ) from exc
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _key_id_from_public_key(public_key_raw: bytes) -> str:
    return hashlib.sha256(public_key_raw).hexdigest()[:16]


def _legacy_key_id(signer_key: str) -> str:
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


def _load_trusted_signers() -> dict[str, dict[str, Any]]:
    try:
        root = json.loads(_TRUST_ROOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    signers = root.get("signers")
    if not isinstance(signers, list):
        return {}
    trusted: dict[str, dict[str, Any]] = {}
    for signer in signers:
        if not isinstance(signer, dict):
            continue
        key_id = signer.get("key_id")
        if isinstance(key_id, str) and key_id:
            trusted[key_id] = signer
    return trusted


def _statement_algorithm(statement: dict[str, Any]) -> str:
    signature = statement.get("signature")
    if isinstance(signature, dict) and isinstance(signature.get("alg"), str):
        return str(signature.get("alg"))
    signer = statement.get("signer")
    if isinstance(signer, dict) and isinstance(signer.get("algorithm"), str):
        return str(signer.get("algorithm"))
    predicate = statement.get("predicate")
    if isinstance(predicate, dict):
        metadata = predicate.get("metadata")
        if isinstance(metadata, dict):
            signer_meta = metadata.get("signer")
            if isinstance(signer_meta, dict) and isinstance(signer_meta.get("algorithm"), str):
                return str(signer_meta.get("algorithm"))
    return ""


def _statement_key_id(statement: dict[str, Any]) -> str:
    signature = statement.get("signature")
    if isinstance(signature, dict) and isinstance(signature.get("keyid"), str):
        return str(signature.get("keyid"))
    signer = statement.get("signer")
    if isinstance(signer, dict) and isinstance(signer.get("keyid"), str):
        return str(signer.get("keyid"))
    predicate = statement.get("predicate")
    if isinstance(predicate, dict):
        metadata = predicate.get("metadata")
        if isinstance(metadata, dict):
            signer_meta = metadata.get("signer")
            if isinstance(signer_meta, dict) and isinstance(signer_meta.get("keyid"), str):
                return str(signer_meta.get("keyid"))
    return ""


def _parse_minisign_detached(value: str, trusted_comment_hint: str | None) -> tuple[bytes, str | None, bytes | None]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) >= 2 and lines[0].startswith("untrusted comment:"):
        try:
            signature = base64.b64decode(lines[1], validate=True)
        except Exception as exc:
            raise ValueError("invalid_signature_encoding") from exc
        trusted_comment = None
        trusted_comment_sig = None
        if len(lines) >= 4 and lines[2].startswith("trusted comment:"):
            trusted_comment = lines[2].split(":", 1)[1].strip()
            try:
                trusted_comment_sig = base64.b64decode(lines[3], validate=True)
            except Exception as exc:
                raise ValueError("invalid_trusted_comment_signature") from exc
        elif trusted_comment_hint:
            trusted_comment = trusted_comment_hint
        return signature, trusted_comment, trusted_comment_sig
    try:
        signature = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("invalid_signature_encoding") from exc
    return signature, trusted_comment_hint, None


def _resolve_legacy_hmac_secret(key_id: str, signer_pubkey: str | None) -> str | None:
    if signer_pubkey:
        expected = _legacy_key_id(signer_pubkey)
        if expected == key_id:
            return signer_pubkey
    raw_map = os.getenv("OMG_LEGACY_HMAC_KEYS", "")
    if raw_map:
        try:
            mapping = json.loads(raw_map)
        except json.JSONDecodeError:
            mapping = {}
        if isinstance(mapping, dict):
            secret = mapping.get(key_id)
            if isinstance(secret, str) and secret:
                return secret
    specific = os.getenv(f"OMG_LEGACY_HMAC_KEY_{key_id.upper()}", "")
    return specific or None


def sign_artifact(
    artifact_path: str,
    subject_digest: str,
    signer_key_id: str = _DEFAULT_DEV_SIGNER_KEY_ID,
    signer_private_key: str | None = None,
    trusted_comment: str | None = None,
    signing_payload: dict[str, object] | None = None,
) -> dict[str, str]:
    clean_path = str(artifact_path).strip()
    clean_digest = str(subject_digest).strip().lower()
    if not clean_path:
        raise ValueError("artifact_path_required")
    if len(clean_digest) != 64 or any(ch not in "0123456789abcdef" for ch in clean_digest):
        raise ValueError("subject_digest_must_be_sha256_hex")

    serialization, Ed25519PrivateKey, _ = _load_ed25519_backend()

    if signer_private_key:
        private_raw = base64.b64decode(signer_private_key, validate=True)
        if len(private_raw) != 32:
            raise ValueError("signer_private_key_must_be_base64_32_bytes")
        private_key = Ed25519PrivateKey.from_private_bytes(private_raw)
    else:
        private_key = Ed25519PrivateKey.generate()

    public_key_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = _key_id_from_public_key(public_key_raw)
    if signer_private_key and signer_key_id != key_id:
        raise ValueError("signer_key_id_mismatch")

    issued_at = _utc_now()
    trusted = trusted_comment or (
        f"type=omg-slsa-v1 keyid={key_id} issued_at={issued_at} artifact={clean_path} sha256={clean_digest}"
    )
    payload: dict[str, object]
    if signing_payload is None:
        payload = {
            "artifact_path": clean_path,
            "subject_digest": clean_digest,
            "issued_at": issued_at,
            "signer_key_id": key_id,
            "algorithm": "ed25519-minisign",
        }
    else:
        payload = signing_payload
    detached_signature = private_key.sign(_canonical_json(payload))
    trusted_comment_signature = private_key.sign(trusted.encode("utf-8"))
    minisign_signature = "\n".join(
        [
            "untrusted comment: signature from omg local signing key",
            base64.b64encode(detached_signature).decode("ascii"),
            f"trusted comment: {trusted}",
            base64.b64encode(trusted_comment_signature).decode("ascii"),
        ]
    )
    return {
        "algorithm": "ed25519-minisign",
        "signature": minisign_signature,
        "signer_key_id": key_id,
        "trusted_comment": trusted,
    }


def sign_artifact_statement(
    artifact_path: str,
    subject_digest: str,
    signer_key: str | None = None,
    signer_key_id: str = _DEFAULT_DEV_SIGNER_KEY_ID,
    trusted_comment: str | None = None,
) -> dict[str, Any]:
    issued_at = _utc_now()
    statement: dict[str, Any] = {
        "_type": _IN_TOTO_STATEMENT_TYPE,
        "predicateType": _SLSA_PREDICATE_TYPE,
        "subject": [
            {
                "name": str(artifact_path).strip(),
                "digest": {"sha256": str(subject_digest).strip().lower()},
            }
        ],
        "predicate": {
            "buildType": "https://omg.security/offline-attestation/v1",
            "metadata": {
                "signer": {
                    "keyid": signer_key_id,
                    "algorithm": "ed25519-minisign",
                    "mode": "local-offline",
                },
                "timestamp": issued_at,
            },
        },
        "signer": {
            "keyid": signer_key_id,
            "algorithm": "ed25519-minisign",
            "mode": "local-offline",
        },
        "issued_at": issued_at,
    }
    signature = sign_artifact(
        artifact_path=artifact_path,
        subject_digest=subject_digest,
        signer_key_id=signer_key_id,
        signer_private_key=signer_key,
        trusted_comment=trusted_comment,
        signing_payload=_statement_signing_payload(statement),
    )
    statement["signature"] = {
        "alg": signature["algorithm"],
        "keyid": signature["signer_key_id"],
        "value": signature["signature"],
        "trusted_comment": signature["trusted_comment"],
    }
    return statement


def _verify_ed25519_statement(statement: dict[str, Any]) -> tuple[bool, str]:
    try:
        _, _, Ed25519PublicKey = _load_ed25519_backend()
    except ModuleNotFoundError as exc:
        return False, str(exc)

    key_id = _statement_key_id(statement)
    if not key_id:
        return False, "missing signer key id"

    trusted_signers = _load_trusted_signers()
    signer = trusted_signers.get(key_id)
    if signer is None:
        return False, "unknown signer key id"
    if str(signer.get("algorithm", "")) != "ed25519-minisign":
        return False, "algorithm mismatch for trusted signer"

    public_key_b64 = signer.get("public_key")
    if not isinstance(public_key_b64, str) or not public_key_b64:
        return False, "invalid trusted signer public key"
    try:
        public_key_raw = base64.b64decode(public_key_b64, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_raw)
    except Exception:
        return False, "invalid trusted signer public key"

    if _key_id_from_public_key(public_key_raw) != key_id:
        return False, "trusted signer key id mismatch"

    signature = statement.get("signature")
    if not isinstance(signature, dict):
        return False, "missing signature object"
    signature_value = signature.get("value")
    if not isinstance(signature_value, str):
        return False, "missing signature value"

    trusted_comment_hint = signature.get("trusted_comment")
    if trusted_comment_hint is not None and not isinstance(trusted_comment_hint, str):
        return False, "invalid trusted comment"

    try:
        detached_sig, trusted_comment, trusted_comment_sig = _parse_minisign_detached(signature_value, trusted_comment_hint)
    except ValueError as exc:
        return False, str(exc)

    try:
        public_key.verify(detached_sig, _canonical_json(_statement_signing_payload(statement)))
    except Exception:
        return False, "invalid attestation signature"

    if trusted_comment and trusted_comment_sig:
        try:
            public_key.verify(trusted_comment_sig, trusted_comment.encode("utf-8"))
        except Exception:
            return False, "invalid trusted comment signature"

    return True, "verified"


def _verify_hmac_bridge_statement(statement: dict[str, Any], signer_pubkey: str | None = None) -> tuple[bool, str]:
    key_id = _statement_key_id(statement)
    if not key_id:
        return False, "missing signer key id"

    secret = _resolve_legacy_hmac_secret(key_id=key_id, signer_pubkey=signer_pubkey)
    if not secret:
        return False, "missing legacy hmac bridge key"

    signature = statement.get("signature")
    if not isinstance(signature, dict):
        return False, "missing signature object"
    if str(signature.get("alg", "")) != "hmac-sha256":
        return False, "signature algorithm mismatch"
    try:
        actual_sig = base64.b64decode(str(signature.get("value", "")), validate=True)
    except Exception:
        return False, "invalid signature encoding"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        _canonical_json(_statement_signing_payload(statement)),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(actual_sig, expected_sig):
        return False, "invalid legacy hmac signature"
    return True, "verified"


def verify_artifact_statement(statement: dict[str, Any], signer_pubkey: str | None = None) -> bool:
    if not isinstance(statement, dict):
        return False
    if str(statement.get("_type", "")) != _IN_TOTO_STATEMENT_TYPE:
        return False
    if str(statement.get("predicateType", "")) != _SLSA_PREDICATE_TYPE:
        return False
    if not _subject_is_valid(statement.get("subject")):
        return False

    algorithm = _statement_algorithm(statement)
    if algorithm == "ed25519-minisign":
        ok, _reason = _verify_ed25519_statement(statement)
        return ok
    if algorithm == "hmac-sha256":
        ok, _reason = _verify_hmac_bridge_statement(statement, signer_pubkey=signer_pubkey)
        return ok
    return False


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


def _verify_statement_with_bridge(statement: dict[str, Any]) -> tuple[str, str]:
    algorithm = _statement_algorithm(statement)
    if algorithm == "ed25519-minisign":
        ok, reason = _verify_ed25519_statement(statement)
        return ("allow", "artifact verified") if ok else ("block", reason)
    if algorithm == "hmac-sha256":
        ok, reason = _verify_hmac_bridge_statement(statement)
        return ("allow", "artifact verified") if ok else ("block", reason)
    return "block", f"unsupported signing algorithm: {algorithm or 'missing'}"


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

    if not a.attestation:
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

    verify_action, verify_reason = _verify_statement_with_bridge(a.attestation)
    if verify_action == "block":
        return {
            "action": "block",
            "risk_level": "high",
            "reason": verify_reason,
            "controls": ["manual-approval", "forensic-review"],
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
