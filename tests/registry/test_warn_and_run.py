"""Tests for registry warn-and-run verification."""

import hashlib

from registry.verify_artifact import (
    sign_artifact_statement,
    verify_artifact,
    verify_artifact_statement,
)


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


def test_verified_artifact_allows():
    digest = hashlib.sha256(b"pkg-c").hexdigest()
    signer_key = "local-secret"
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-c.whl",
        signer_key=signer_key,
        subject_digest=digest,
    )
    result = verify_artifact(
        {
            "id": "pkg-c",
            "signer": "trusted",
            "checksum": "sha256:abc",
            "signer_pubkey": signer_key,
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
            "risk_level": "low",
        }
    )
    assert result["action"] == "allow"
    assert result["trusted"] is True


def test_sign_and_verify_statement_offline():
    digest = hashlib.sha256(b"forge-checkpoint").hexdigest()
    signer_key = "checkpoint-secret"

    statement = sign_artifact_statement(
        artifact_path="checkpoints/model.bin",
        signer_key=signer_key,
        subject_digest=digest,
    )

    assert statement["_type"].startswith("https://in-toto.io/Statement")
    assert statement["subject"][0]["digest"]["sha256"] == digest
    assert verify_artifact_statement(statement, signer_pubkey=signer_key) is True


def test_invalid_attestation_blocks_trust():
    digest = hashlib.sha256(b"pkg-d").hexdigest()
    signer_key = "local-secret"
    statement = sign_artifact_statement(
        artifact_path="dist/public/pkg-d.whl",
        signer_key=signer_key,
        subject_digest=digest,
    )
    statement["subject"][0]["digest"]["sha256"] = hashlib.sha256(b"tampered").hexdigest()

    result = verify_artifact(
        {
            "id": "pkg-d",
            "signer": "trusted",
            "checksum": "sha256:def",
            "signer_pubkey": signer_key,
            "attestation": statement,
            "permissions": ["Read"],
            "static_scan": [],
            "risk_level": "low",
        },
        mode="strict",
    )

    assert result["action"] == "deny"
    assert result["trusted"] is False
