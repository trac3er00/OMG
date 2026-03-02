"""Behavior tests for stop-gate.py completion gating."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
STOP_GATE = ROOT / "hooks" / "stop-gate.py"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_ledger(project: Path, entries: list[dict]) -> Path:
    ledger = project / ".oal" / "state" / "ledger" / "tool-ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("w", encoding="utf-8") as f:
        for entry in entries:
            payload = {"ts": _now_iso(), **entry}
            f.write(json.dumps(payload) + "\n")
    return ledger


def _run_stop_gate(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(STOP_GATE)],
        input="{}",
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        check=False,
    )


def _decision(proc: subprocess.CompletedProcess[str]) -> dict:
    out = proc.stdout.strip()
    if not out:
        return {}
    return json.loads(out)


def test_internal_oal_writes_do_not_trigger_evidence_block(tmp_path: Path):
    project = tmp_path
    (project / ".oal").mkdir(parents=True, exist_ok=True)
    (project / ".oal" / "policy.yaml").write_text(
        "mode: warn_and_run\nrequire_evidence_pack: true\n",
        encoding="utf-8",
    )

    _write_ledger(
        project,
        [
            {"tool": "Write", "file": ".oal/state/_plan.md", "success": True},
        ],
    )

    proc = _run_stop_gate(project)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_source_writes_require_evidence_in_strict_mode(tmp_path: Path):
    project = tmp_path
    (project / ".oal").mkdir(parents=True, exist_ok=True)
    (project / ".oal" / "policy.yaml").write_text(
        "mode: strict\nrequire_evidence_pack: true\n",
        encoding="utf-8",
    )

    _write_ledger(
        project,
        [
            {"tool": "Write", "file": "src/app.py", "success": True},
            {"tool": "Bash", "command": "pytest -q", "exit_code": 0},
        ],
    )

    proc = _run_stop_gate(project)
    assert proc.returncode == 0
    decision = _decision(proc)
    assert decision.get("decision") == "block"
    assert "evidence gate" in decision.get("reason", "").lower()


def test_source_writes_warn_mode_emits_advisory_not_block(tmp_path: Path):
    project = tmp_path
    (project / ".oal").mkdir(parents=True, exist_ok=True)
    (project / ".oal" / "policy.yaml").write_text(
        "mode: warn_and_run\nrequire_evidence_pack: true\n",
        encoding="utf-8",
    )

    _write_ledger(
        project,
        [
            {"tool": "Write", "file": "src/app.py", "success": True},
            {"tool": "Bash", "command": "pytest -q", "exit_code": 0},
        ],
    )

    proc = _run_stop_gate(project)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert "oal advisory" in proc.stderr.lower()


def test_write_failure_check_ignores_internal_and_unknown_status(tmp_path: Path):
    project = tmp_path
    _write_ledger(
        project,
        [
            {"tool": "Write", "file": "src/app.py", "success": True},
            {"tool": "Bash", "command": "pytest -q", "exit_code": 0},
            {"tool": "Write", "file": ".omc/_checklist.md", "success": False},
            {"tool": "Write", "file": "src/other.py", "success": None},
        ],
    )

    proc = _run_stop_gate(project)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_write_failure_check_blocks_explicit_source_write_failures(tmp_path: Path):
    project = tmp_path
    _write_ledger(
        project,
        [
            {"tool": "Write", "file": "src/app.py", "success": True},
            {"tool": "Bash", "command": "pytest -q", "exit_code": 0},
            {"tool": "Write", "file": "src/bad.py", "success": False},
        ],
    )

    proc = _run_stop_gate(project)
    assert proc.returncode == 0
    decision = _decision(proc)
    assert decision.get("decision") == "block"
    reason = decision.get("reason", "")
    assert "WRITE/EDIT FAILURE DETECTED" in reason
    assert "src/bad.py" in reason
