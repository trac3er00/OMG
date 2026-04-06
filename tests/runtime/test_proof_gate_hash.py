from __future__ import annotations

import hashlib
from pathlib import Path

from runtime import proof_gate


validate_artifact_hash = getattr(proof_gate, "_validate_artifact_hash")


def test_artifact_missing_sha256_returns_blocker() -> None:
    artifact = {"path": "/tmp/test.txt", "kind": "test_output"}

    result = validate_artifact_hash(artifact)

    assert result is not None, "Expected blocker string but got None"
    assert "missing" in result.lower() or "hash" in result.lower()


def test_artifact_invalid_sha256_format_returns_blocker() -> None:
    artifact = {"path": "/tmp/test.txt", "kind": "test_output", "sha256": "tooshort"}

    result = validate_artifact_hash(artifact)

    assert result is not None, "Expected blocker string but got None"
    assert (
        "invalid" in result.lower()
        or "hash" in result.lower()
        or "format" in result.lower()
    )


def test_artifact_missing_path_returns_blocker() -> None:
    artifact = {"sha256": "a" * 64, "kind": "test_output"}

    result = validate_artifact_hash(artifact)

    assert result is not None, "Expected blocker for missing path"


def test_artifact_with_valid_sha256_passes(tmp_path: Path) -> None:
    test_file = tmp_path / "test.txt"
    _ = test_file.write_text("hello world", encoding="utf-8")
    correct_sha256 = hashlib.sha256(test_file.read_bytes()).hexdigest()
    artifact = {"path": str(test_file), "kind": "test_output", "sha256": correct_sha256}

    result = validate_artifact_hash(artifact)

    assert result is None, f"Expected None (pass) but got: {result}"


def test_artifact_sha256_mismatch_returns_blocker(tmp_path: Path) -> None:
    test_file = tmp_path / "test.txt"
    _ = test_file.write_text("hello world", encoding="utf-8")
    wrong_sha256 = "a" * 64
    artifact = {"path": str(test_file), "kind": "test_output", "sha256": wrong_sha256}

    result = validate_artifact_hash(artifact)

    assert result is not None
    assert "mismatch" in result.lower()
