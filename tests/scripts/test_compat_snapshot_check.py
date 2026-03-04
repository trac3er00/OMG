"""Tests for compatibility snapshot checker scripts."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-omg-compat-contract-snapshot.py"
SNAPSHOT = ROOT / "runtime" / "omg_compat_contract_snapshot.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_snapshot_check_passes_on_current_snapshot():
    proc = _run(["--strict-version"])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"


def test_snapshot_check_detects_drift(tmp_path: Path):
    broken = tmp_path / "broken-snapshot.json"
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    payload["count"] = 0
    broken.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = _run(["--snapshot", str(broken)])
    assert proc.returncode != 0
    out = json.loads(proc.stdout)
    assert out["status"] == "error"
    assert "drift" in out["message"]


def test_legacy_checker_wrapper_still_works():
    legacy_checker = ROOT / "scripts" / "check-omg-contract-snapshot.py"
    proc = subprocess.run(
        [sys.executable, str(legacy_checker), "--strict-version"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
