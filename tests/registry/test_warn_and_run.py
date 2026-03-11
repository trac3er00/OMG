"""Tests for registry warn-and-run verification."""

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from registry.verify_artifact import sign_artifact, sign_artifact_statement, verify_artifact


_DEV_PRIVATE_KEY = "Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8="
_DEV_KEY_ID = "1f5fe64ec2f8c901"


def _key_id_from_private_key(private_key_b64: str) -> str:
    private_raw = base64.b64decode(private_key_b64)
    public_raw = (
        Ed25519PrivateKey.from_private_bytes(private_raw)
        .public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    )
    return hashlib.sha256(public_raw).hexdigest()[:16]


def _legacy_statement(secret: str, digest: str) -> dict[str, Any]:
    key_id = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    statement: dict[str, object] = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [{"name": "dist/public/pkg-legacy.whl", "digest": {"sha256": digest}}],
        "predicate": {
            "buildType": "https://omg.security/offline-attestation/v1",
            "metadata": {
                "signer": {
                    "keyid": key_id,
                    "algorithm": "hmac-sha256",
                    "mode": "local-offline",
                },
                "timestamp": "2026-03-10T00:00:00+00:00",
            },
        },
        "signer": {
            "keyid": key_id,
            "algorithm": "hmac-sha256",
            "mode": "local-offline",
        },
        "issued_at": "2026-03-10T00:00:00+00:00",
    }
    payload = {
        "_type": statement.get("_type"),
        "predicateType": statement.get("predicateType"),
        "subject": statement.get("subject"),
        "predicate": statement.get("predicate"),
        "signer": statement.get("signer"),
        "issued_at": statement.get("issued_at"),
    }
    signature = hmac.new(
        secret.encode("utf-8"),
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    statement["signature"] = {
        "alg": "hmac-sha256",
        "keyid": key_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return statement


def test_warn_and_run_unsigned_returns_ask():
    result = verify_artifact(
        {
            "id": "pkg-a",
            "permissions": ["Read", "Write"],
            "static_scan": [],
        },
        mode="warn_and_run",
    )
    assert result["action"] == "ask"
    assert result["risk_level"] == "high"


def test_critical_findings_always_block():
    result = verify_artifact(
        {
            "id": "pkg-b",
            "signer": "ok",
            "checksum": "123",
            "permissions": ["Read"],
            "static_scan": [{"severity": "critical", "rule": "rce"}],
        },
        mode="warn_and_run",
    )
    assert result["action"] == "deny"
    assert result["risk_level"] == "critical"


def test_known_key_valid_ed25519_signature_allows():
    digest = hashlib.sha256(b"pkg-c").hexdigest()
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-c.whl",
        signer_key=_DEV_PRIVATE_KEY,
        signer_key_id=_DEV_KEY_ID,
        subject_digest=digest,
    )
    result = verify_artifact(
        {
            "id": "pkg-c",
            "signer": "trusted",
            "checksum": "sha256:abc",
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
            "risk_level": "low",
        }
    )
    assert statement["signature"]["alg"] == "ed25519-minisign"
    assert result["action"] == "allow"


def test_unknown_key_is_blocked():
    unknown_private = "ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA="
    unknown_key_id = _key_id_from_private_key(unknown_private)
    digest = hashlib.sha256(b"pkg-unknown").hexdigest()
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-unknown.whl",
        signer_key=unknown_private,
        signer_key_id=unknown_key_id,
        subject_digest=digest,
    )

    result = verify_artifact(
        {
            "id": "pkg-unknown",
            "signer": "unknown",
            "checksum": "sha256:111",
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
        }
    )
    assert result["action"] == "block"


def test_tampered_signature_is_blocked():
    digest = hashlib.sha256(b"pkg-d").hexdigest()
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-d.whl",
        signer_key=_DEV_PRIVATE_KEY,
        signer_key_id=_DEV_KEY_ID,
        subject_digest=digest,
    )
    signature_lines = statement["signature"]["value"].splitlines()
    signature_lines[1] = base64.b64encode(b"tampered-signature").decode("ascii")
    statement["signature"]["value"] = "\n".join(signature_lines)

    result = verify_artifact(
        {
            "id": "pkg-d",
            "signer": "trusted",
            "checksum": "sha256:def",
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
            "risk_level": "low",
        },
        mode="strict",
    )
    assert result["action"] == "block"
    assert result["trusted"] is False


def test_legacy_hmac_fixture_verifies_via_bridge(monkeypatch):
    digest = hashlib.sha256(b"pkg-legacy").hexdigest()
    secret = "legacy-secret"
    statement = _legacy_statement(secret=secret, digest=digest)
    key_id = statement["signature"]["keyid"]
    monkeypatch.setenv("OMG_LEGACY_HMAC_KEYS", json.dumps({key_id: secret}))

    result = verify_artifact(
        {
            "id": "pkg-legacy",
            "signer": "legacy",
            "checksum": "sha256:legacy",
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
        },
    )
    assert result["action"] == "allow"


def test_new_signing_path_never_emits_hmac_sha256():
    digest = hashlib.sha256(b"pkg-new").hexdigest()
    detached = sign_artifact(
        artifact_path="dist/public/pkg-new.whl",
        signer_private_key=_DEV_PRIVATE_KEY,
        signer_key_id=_DEV_KEY_ID,
        subject_digest=digest,
    )
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-new.whl",
        signer_key=_DEV_PRIVATE_KEY,
        signer_key_id=_DEV_KEY_ID,
        subject_digest=digest,
    )

    assert detached["algorithm"] == "ed25519-minisign"
    assert statement["signature"]["alg"] == "ed25519-minisign"
    assert detached["algorithm"] != "hmac-sha256"
