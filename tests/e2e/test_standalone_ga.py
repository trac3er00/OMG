"""Standalone GA end-to-end checks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "oal.py"
MIGRATOR = ROOT / "scripts" / "legacy_to_oal_migrate.py"


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def test_standalone_commands_work_without_omc_install(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}

    teams = _run([str(CLI), "teams", "--problem", "debug backend auth flow"], ROOT, env=env)
    assert teams.returncode == 0
    teams_out = json.loads(teams.stdout)
    assert teams_out["status"] == "ok"
    assert teams_out["schema"] == "TeamDispatchResult"

    ccg = _run([str(CLI), "ccg", "--problem", "review full-stack reliability"], ROOT, env=env)
    assert ccg.returncode == 0
    ccg_out = json.loads(ccg.stdout)
    assert ccg_out["status"] == "ok"
    assert ccg_out["evidence"]["target"] == "ccg"


def test_standalone_ship_generates_evidence_without_omc(tmp_path: Path):
    idea = tmp_path / "idea.json"
    idea.write_text(json.dumps({"goal": "ship standalone test"}), encoding="utf-8")

    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    ship = _run([str(CLI), "ship", "--runtime", "claude", "--idea", str(idea)], ROOT, env=env)
    assert ship.returncode == 0
    out = json.loads(ship.stdout)
    assert out["status"] == "ok"

    evidence_path = tmp_path / out["evidence_path"]
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "EvidencePack"


def test_migration_cli_no_legacy_is_safe(tmp_path: Path):
    proc = _run([str(MIGRATOR), "--project-dir", str(tmp_path)], ROOT, env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["result"] == "no_legacy"
    assert (tmp_path / ".oal" / "migrations" / "legacy-to-oal.json").exists()
    assert (tmp_path / ".oal" / "migrations" / "omc-to-oal.json").exists()


def test_migration_legacy_wrapper_still_works(tmp_path: Path):
    wrapper = ROOT / "scripts" / "omc_to_oal_migrate.py"
    proc = _run([str(wrapper), "--project-dir", str(tmp_path)], ROOT, env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert proc.returncode == 0


def test_compliance_artifacts_exist():
    notices_path = ROOT / "THIRD_PARTY_NOTICES.md"
    upstream_path = ROOT / "UPSTREAM_DIFF.md"
    vendor_license = ROOT / "vendor" / "omc" / "LICENSE"

    assert notices_path.exists()
    assert upstream_path.exists()

    notices = notices_path.read_text(encoding="utf-8")
    upstream = upstream_path.read_text(encoding="utf-8")
    assert "Initial imported commit hash" in upstream
    assert "oh-my-claudecode" in notices
    assert "Repository:" in notices

    # Full repo may include vendored payload. Standalone bundle may omit it.
    if (ROOT / "vendor" / "omc").exists():
        assert "vendor/omc" in notices
        assert vendor_license.exists()
    else:
        assert "optional in standalone distributions" in notices
