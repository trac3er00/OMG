"""Tests for scripts/check-omg-standalone-clean.py."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-omg-standalone-clean.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_standalone_clean_check_passes_on_repo():
    proc = _run([])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"


def test_standalone_clean_check_detects_legacy_namespace_violation(tmp_path: Path):
    # Build a minimal fake root containing one violating file.
    (tmp_path / "runtime").mkdir(parents=True)
    bad = tmp_path / "runtime" / "bad.py"
    bad.write_text('print("python3 scripts/omg.py omc list")\n', encoding="utf-8")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"
    assert any("legacy CLI namespace" in v for v in payload["violations"])


def test_standalone_clean_check_detects_legacy_runtime_import(tmp_path: Path):
    (tmp_path / "scripts").mkdir(parents=True)
    bad = tmp_path / "scripts" / "bad.py"
    bad.write_text("from runtime.legacy_compat import list_compat_skills\n", encoding="utf-8")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"
    assert any("legacy runtime import" in v for v in payload["violations"])


def test_standalone_clean_check_detects_legacy_runtime_import_variant(tmp_path: Path):
    (tmp_path / "runtime").mkdir(parents=True)
    bad = tmp_path / "runtime" / "bad.py"
    bad.write_text("import runtime.legacy_compat as legacy\n", encoding="utf-8")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"
    assert any("legacy runtime import" in v for v in payload["violations"])
