#!/usr/bin/env python3
"""Tests for runtime.verification_controller proof automation API."""
from pathlib import Path

import pytest

from runtime.verification_controller import auto_verify, enable_proof_by_default


def test_auto_verify_returns_dict(tmp_path: Path) -> None:
    """Verify auto_verify returns a dict."""
    result = auto_verify({"success": True}, str(tmp_path))

    assert isinstance(result, dict)


def test_auto_verify_creates_evidence(tmp_path: Path) -> None:
    """Verify auto_verify creates evidence file."""
    result = auto_verify({"success": True, "run_id": "test-run"}, str(tmp_path))

    evidence_dir = tmp_path / ".omg" / "evidence"
    assert evidence_dir.exists()

    evidence_files = list(evidence_dir.glob("*-auto.json"))
    assert len(evidence_files) >= 1


def test_enable_proof_by_default(tmp_path: Path) -> None:
    """Verify enable_proof_by_default exists and is callable."""
    assert callable(enable_proof_by_default)

    enable_proof_by_default(str(tmp_path))

    config_path = tmp_path / ".omg" / "state" / "verification_controller" / "proof-by-default.json"
    assert config_path.exists()
