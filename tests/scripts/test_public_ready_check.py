"""Tests for scripts/check-omg-public-ready.py."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-omg-public-ready.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_public_ready_check_passes_on_repo():
    proc = _run([])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"


def test_public_ready_check_detects_absolute_local_paths(tmp_path: Path):
    _write(tmp_path / "README.md", "[doc](/Users/example/private/doc.md)\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "error"
    assert any("absolute local path" in violation for violation in payload["violations"])


def test_public_ready_check_detects_internal_docs_directory(tmp_path: Path):
    _write(tmp_path / "README.md", "# readme\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")
    _write(tmp_path / "docs" / "plans" / "private.md", "# private plan\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any("internal planning docs" in violation for violation in payload["violations"])


def test_public_ready_check_detects_stale_internal_reference(tmp_path: Path):
    _write(tmp_path / "README.md", "# readme\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")
    _write(tmp_path / "hooks" / "credential_store.py", '"""Design ref: .sisyphus/credential-store-design.md"""\n')

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any(".sisyphus/" in violation for violation in payload["violations"])


def test_public_ready_check_detects_old_repo_identifier(tmp_path: Path):
    _write(tmp_path / "README.md", "Repo: trac3er00/OAL\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any("old repo identifier" in violation for violation in payload["violations"])


def test_public_ready_check_detects_missing_community_docs(tmp_path: Path):
    _write(tmp_path / "README.md", "# readme\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any("missing required public doc" in violation for violation in payload["violations"])


def test_public_ready_check_detects_missing_issue_and_pr_templates(tmp_path: Path):
    _write(tmp_path / "README.md", "# readme\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any("missing required community template" in violation for violation in payload["violations"])


def test_public_ready_check_detects_broken_relative_markdown_link(tmp_path: Path):
    _write(tmp_path / "README.md", "[proof](docs/proof.md)\n")
    _write(tmp_path / "CONTRIBUTING.md", "# contributing\n")
    _write(tmp_path / "SECURITY.md", "# security\n")
    _write(tmp_path / "CODE_OF_CONDUCT.md", "# code of conduct\n")
    _write(tmp_path / "CHANGELOG.md", "# changelog\n")

    proc = _run(["--root", str(tmp_path)])
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert any("broken markdown link" in violation for violation in payload["violations"])
