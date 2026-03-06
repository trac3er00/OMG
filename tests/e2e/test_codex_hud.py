"""Smoke tests for the standalone Codex OMG HUD/workbench script."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "codex-hud" / "omg_codex_hud.py"
HUD_WRAPPER = ROOT / "codex-hud" / "omg-codex-hud"


def _run_hud(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(HUD), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def _run_hud_wrapper(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    merged_env.update(env)
    return subprocess.run(
        [str(HUD_WRAPPER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def test_codex_hud_json_reports_project_state_and_installed_skills(tmp_path: Path):
    project = tmp_path / "project"
    state = project / ".omg" / "state"
    knowledge = project / ".omg" / "knowledge"
    state.mkdir(parents=True)
    knowledge.mkdir(parents=True)
    _ = (state / "mode.txt").write_text("implement\n", encoding="utf-8")
    _ = (state / "handoff.md").write_text("# handoff\n", encoding="utf-8")
    _ = (knowledge / "notes.md").write_text("note\n", encoding="utf-8")

    codex_home = tmp_path / ".codex"
    skill_dir = codex_home / "skills" / "omg-codex-workbench"
    skill_dir.mkdir(parents=True)
    _ = (skill_dir / ".omg-managed-skill").write_text("omg-codex-skill-v1\n", encoding="utf-8")

    proc = _run_hud(["--project", str(project), "--json"], {"CODEX_HOME": str(codex_home)})

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "OmgCodexHud"
    assert payload["project"]["mode"] == "implement"
    assert payload["project"]["handoff_present"] is True
    assert "omg-codex-workbench" in payload["codex"]["omg_skills"]


def test_codex_hud_text_output_mentions_mode_and_skills(tmp_path: Path):
    project = tmp_path / "project"
    state = project / ".omg" / "state"
    state.mkdir(parents=True)
    _ = (state / "mode.txt").write_text("research\n", encoding="utf-8")

    codex_home = tmp_path / ".codex"
    skill_dir = codex_home / "skills" / "omg-review-gate"
    skill_dir.mkdir(parents=True)
    _ = (skill_dir / ".omg-managed-skill").write_text("omg-codex-skill-v1\n", encoding="utf-8")

    proc = _run_hud(["--project", str(project)], {"CODEX_HOME": str(codex_home)})

    assert proc.returncode == 0
    out = proc.stdout.lower()
    assert "omg codex hud" in out
    assert "mode: research" in out
    assert "omg-review-gate" in out


def test_codex_hud_wrapper_runs_from_repo_checkout(tmp_path: Path):
    project = tmp_path / "project"
    (project / ".omg" / "state").mkdir(parents=True)

    proc = _run_hud_wrapper(["--project", str(project)], {"CODEX_HOME": str(tmp_path / ".codex")})

    assert proc.returncode == 0
    assert "OMG Codex HUD" in proc.stdout
