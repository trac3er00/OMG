"""Behavior-level e2e checks for native-promoted compatibility skills."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "omg.py"


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


def test_autopilot_then_cancel_updates_persistent_state(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    auto = _run([str(CLI), "compat", "run", "--skill", "autopilot", "--problem", "iterate"], ROOT, env=env)
    assert auto.returncode == 0
    state_path = tmp_path / ".omg" / "state" / "persistent-mode.json"
    assert state_path.exists()

    cancel = _run([str(CLI), "compat", "run", "--skill", "cancel"], ROOT, env=env)
    assert cancel.returncode == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "cancelled"


def test_native_artifact_generators(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    for skill, rel in [
        ("build-fix", ".omg/state/build-fix.md"),
        ("release", ".omg/evidence/release-draft.md"),
        ("analyze", ".omg/evidence/analysis-analyze.json"),
        ("trace", ".omg/evidence/analysis-trace.json"),
        ("learner", ".omg/knowledge/learning/learner.md"),
        ("note", ".omg/knowledge/notes.md"),
        ("writer-memory", ".omg/knowledge/writer-memory.md"),
    ]:
        proc = _run([str(CLI), "compat", "run", "--skill", skill, "--problem", f"e2e {skill}"], ROOT, env=env)
        assert proc.returncode == 0, f"{skill} failed: {proc.stdout}\n{proc.stderr}"
        assert (tmp_path / rel).exists(), f"missing artifact for {skill}: {rel}"


def test_compat_gate_zero_bridge(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    gate = _run([str(CLI), "compat", "gate", "--max-bridge", "0"], ROOT, env=env)
    assert gate.returncode == 0
    payload = json.loads(gate.stdout)
    assert payload["status"] == "ok"
    assert payload["report"]["maturity_counts"].get("bridge", 0) == 0


def test_compat_gap_report_uses_project_evidence_dir_by_default(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    report = _run([str(CLI), "compat", "gap-report"], ROOT, env=env)
    assert report.returncode == 0
    payload = json.loads(report.stdout)
    assert payload["status"] == "ok"
    assert (tmp_path / ".omg" / "evidence" / "omg-compat-gap.json").exists()
