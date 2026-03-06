"""Checks for standalone verification script safety."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_verify_standalone_excludes_legacy_omc_dir():
    script = (ROOT / "scripts" / "verify-standalone.sh").read_text(encoding="utf-8")
    assert '--exclude="./.omc"' in script
