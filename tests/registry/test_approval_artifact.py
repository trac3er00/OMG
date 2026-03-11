"""Tests for signed approval artifacts."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from registry.approval_artifact import (
    ApprovalArtifact,
    create_approval_artifact,
    load_approval_artifact_from_path,
    verify_approval_artifact,
)

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


def test_valid_approval_artifact_verifies():
    digest = hashlib.sha256(b"test-artifact-content").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="allow",
        scope="release/v1.0",
        reason="Manual review completed",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )

    assert isinstance(approval, ApprovalArtifact)
    assert approval.artifact_digest == digest
    assert approval.action == "allow"
    assert approval.signature != ""

    result = verify_approval_artifact(approval, expected_artifact_digest=digest)
    assert result["valid"] is True
    assert result["reason"] == "verified"


def test_digest_mismatch_rejected():
    digest_a = hashlib.sha256(b"artifact-a").hexdigest()
    digest_b = hashlib.sha256(b"artifact-b").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest_a,
        action="allow",
        scope="release/v1.0",
        reason="Approved",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )

    result = verify_approval_artifact(approval, expected_artifact_digest=digest_b)
    assert result["valid"] is False
    assert "digest mismatch" in result["reason"]


def test_unknown_signer_key_rejected():
    unknown_private = "ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA="
    unknown_key_id = _key_id_from_private_key(unknown_private)
    digest = hashlib.sha256(b"test-unknown-key").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="allow",
        scope="release/v1.0",
        reason="Approved",
        signer_key_id=unknown_key_id,
        signer_private_key=unknown_private,
    )

    result = verify_approval_artifact(approval, expected_artifact_digest=digest)
    assert result["valid"] is False
    assert "unknown signer" in result["reason"]


def test_tampered_signature_rejected():
    digest = hashlib.sha256(b"test-tampered").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="allow",
        scope="release/v1.0",
        reason="Approved",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )

    lines = approval.signature.splitlines()
    lines[1] = base64.b64encode(b"tampered-garbage-sig-data-here!!").decode("ascii")
    approval.signature = "\n".join(lines)

    result = verify_approval_artifact(approval, expected_artifact_digest=digest)
    assert result["valid"] is False
    assert "invalid" in result["reason"].lower()


def test_missing_signature_rejected():
    digest = hashlib.sha256(b"test-unsigned").hexdigest()

    unsigned_dict = {
        "artifact_digest": digest,
        "action": "allow",
        "scope": "release/v1.0",
        "reason": "Approved",
        "signer_key_id": _DEV_KEY_ID,
        "issued_at": "2026-03-10T00:00:00+00:00",
        "signature": "",
    }

    result = verify_approval_artifact(unsigned_dict, expected_artifact_digest=digest)
    assert result["valid"] is False
    assert "missing" in result["reason"].lower() or "empty" in result["reason"].lower()


def test_none_signature_field_rejected():
    digest = hashlib.sha256(b"test-none-sig").hexdigest()

    bad_dict = {
        "artifact_digest": digest,
        "action": "allow",
        "scope": "release/v1.0",
        "reason": "Approved",
        "signer_key_id": _DEV_KEY_ID,
        "issued_at": "2026-03-10T00:00:00+00:00",
        "signature": None,
    }

    result = verify_approval_artifact(bad_dict, expected_artifact_digest=digest)
    assert result["valid"] is False


def test_dict_input_verifies():
    digest = hashlib.sha256(b"test-dict-input").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="approve",
        scope="advisory/pkg-abc",
        reason="Risk accepted",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )

    approval_dict = asdict(approval)
    result = verify_approval_artifact(approval_dict, expected_artifact_digest=digest)
    assert result["valid"] is True
    assert result["reason"] == "verified"


def test_load_from_path_valid(tmp_path):
    digest = hashlib.sha256(b"test-file-load").hexdigest()

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="allow",
        scope="release/v1.0",
        reason="File-based approval",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )

    file_path = tmp_path / "approval.json"
    file_path.write_text(json.dumps(asdict(approval)), encoding="utf-8")

    result = load_approval_artifact_from_path(file_path, expected_artifact_digest=digest)
    assert result["valid"] is True
    assert result["approval"] is not None
    assert result["approval"]["artifact_digest"] == digest


def test_load_from_path_missing_file(tmp_path):
    digest = hashlib.sha256(b"missing").hexdigest()
    result = load_approval_artifact_from_path(tmp_path / "nonexistent.json", expected_artifact_digest=digest)
    assert result["valid"] is False
    assert "not found" in result["reason"]
    assert result["approval"] is None


def test_load_from_path_invalid_json(tmp_path):
    digest = hashlib.sha256(b"bad-json").hexdigest()
    file_path = tmp_path / "bad.json"
    file_path.write_text("not valid json {{{", encoding="utf-8")

    result = load_approval_artifact_from_path(file_path, expected_artifact_digest=digest)
    assert result["valid"] is False
    assert "invalid JSON" in result["reason"]
    assert result["approval"] is None
