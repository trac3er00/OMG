"""Tests for registry warn-and-run verification."""

from registry.verify_artifact import verify_artifact


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
    result = verify_artifact(
        {
            "id": "pkg-c",
            "signer": "trusted",
            "checksum": "sha256:abc",
            "permissions": ["Read"],
            "static_scan": [],
            "risk_level": "low",
        }
    )
    assert result["action"] == "allow"
    assert result["trusted"] is True
