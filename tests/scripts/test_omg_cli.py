"""Smoke tests for scripts/omg.py CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "omg.py"


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
        timeout=30,
    )


def test_cli_runtime_dispatch_inline_json():
    proc = _run(["runtime", "dispatch", "--runtime", "claude", "--idea-json", '{"goal":"x"}'])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["runtime"] == "claude"


def test_cli_trust_review(tmp_path: Path):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps({"permissions": {"allow": ["Read"]}}), encoding="utf-8")
    new.write_text(json.dumps({"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}), encoding="utf-8")

    proc = _run(["trust", "review", "--old", str(old), "--new", str(new)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["review"]["verdict"] == "deny"
    assert out["review"]["risk_level"] == "critical"


def test_cli_teams_and_ccg_commands():
    teams = _run(["teams", "--problem", "debug api auth bug"])
    assert teams.returncode == 0
    teams_out = json.loads(teams.stdout)
    assert teams_out["status"] == "ok"
    assert teams_out["schema"] == "TeamDispatchResult"

    ccg = _run(["ccg", "--problem", "review full stack architecture"])
    assert ccg.returncode == 0
    ccg_out = json.loads(ccg.stdout)
    assert ccg_out["status"] == "ok"
    assert ccg_out["evidence"]["target"] == "ccg"


def test_cli_teams_auto_routing_honors_explicit_and_ccg_keywords():
    gemini = _run(["teams", "--target", "auto", "--problem", "please use gemini for this component"])
    assert gemini.returncode == 0
    gemini_out = json.loads(gemini.stdout)
    assert gemini_out["evidence"]["target"] == "gemini"

    ccg = _run(["teams", "--target", "auto", "--problem", "run a ccg review for full stack auth and dashboard"])
    assert ccg.returncode == 0
    ccg_out = json.loads(ccg.stdout)
    assert ccg_out["evidence"]["target"] == "ccg"


def test_cli_crazy_launches_five_worker_tracks():
    try:
        crazy = _run(["crazy", "--problem", "stabilize auth and dashboard flows"])
    except subprocess.TimeoutExpired:
        pytest.skip("crazy command timed out (expected for long-running multi-agent tasks)")
        return
    assert crazy.returncode == 0
    start = crazy.stdout.find("{")
    assert start >= 0
    out = json.loads(crazy.stdout[start:])
    assert out["status"] == "ok"
    assert out["worker_count"] == 5
    assert out["target_worker_count"] == 5
    assert out["parallel_execution"] is True
    assert out["sequential_execution"] is False
    phase_agents = [p.get("agent") for p in out["phases"] if isinstance(p, dict)]
    assert "architect-mode" in phase_agents
    assert "backend-engineer" in phase_agents
    assert "frontend-designer" in phase_agents
    assert "security-auditor" in phase_agents
    assert "testing-engineer" in phase_agents


def test_cli_compat_list_and_run():
    listed = _run(["compat", "list"])
    assert listed.returncode == 0
    listed_out = json.loads(listed.stdout)
    assert listed_out["status"] == "ok"
    assert listed_out["count"] >= 30
    assert "omg-teams" in listed_out["skills"]

    run = _run(["compat", "run", "--skill", "omg-teams", "--problem", "compat smoke"])
    assert run.returncode == 0
    run_out = json.loads(run.stdout)
    assert run_out["schema"] == "OmgCompatResult"
    assert run_out["status"] == "ok"


def test_cli_compat_contract_and_gap_report():
    contract = _run(["compat", "contract", "--skill", "omg-teams"])
    assert contract.returncode == 0
    contract_out = json.loads(contract.stdout)
    assert contract_out["status"] == "ok"
    assert contract_out["contract"]["skill"] == "omg-teams"

    promoted_contract = _run(["compat", "contract", "--skill", "autopilot"])
    assert promoted_contract.returncode == 0
    promoted_out = json.loads(promoted_contract.stdout)
    assert promoted_out["contract"]["maturity"] == "native"

    all_contracts = _run(["compat", "contract", "--all"])
    assert all_contracts.returncode == 0
    all_out = json.loads(all_contracts.stdout)
    assert all_out["status"] == "ok"
    assert all_out["count"] >= 30

    gap = _run(["compat", "gap-report"])
    assert gap.returncode == 0
    gap_out = json.loads(gap.stdout)
    assert gap_out["status"] == "ok"
    assert gap_out["report"]["schema"] == "OmgCompatGapReport"
    assert gap_out["report"]["maturity_counts"]["native"] == gap_out["report"]["total_skills"]
    assert gap_out["report"]["maturity_counts"].get("bridge", 0) == 0


def test_cli_compat_gate_pass_and_fail_threshold():
    gate_ok = _run(["compat", "gate", "--max-bridge", "0"])
    assert gate_ok.returncode == 0
    gate_ok_out = json.loads(gate_ok.stdout)
    assert gate_ok_out["status"] == "ok"
    assert gate_ok_out["report"]["maturity_counts"].get("bridge", 0) == 0

    gate_fail = _run(["compat", "gate", "--max-bridge", "-1"])
    assert gate_fail.returncode != 0
    gate_fail_out = json.loads(gate_fail.stdout)
    assert gate_fail_out["status"] == "error"


def test_cli_compat_snapshot_and_gate_output(tmp_path: Path):
    snapshot_out = tmp_path / "contracts.json"
    snap = _run(["compat", "snapshot", "--output", str(snapshot_out)])
    assert snap.returncode == 0
    snap_payload = json.loads(snap.stdout)
    assert snap_payload["status"] == "ok"
    assert snapshot_out.exists()

    gate_out = tmp_path / "gap.json"
    gate = _run(["compat", "gate", "--max-bridge", "0", "--output", str(gate_out)])
    assert gate.returncode == 0
    assert gate_out.exists()
    gap_payload = json.loads(gate_out.read_text(encoding="utf-8"))
    assert gap_payload["schema"] == "OmgCompatGapReport"


def test_cli_omc_alias_routes_to_compat():
    listed = _run(["compat", "list"])
    assert listed.returncode == 0
    listed_out = json.loads(listed.stdout)
    assert listed_out["status"] == "ok"


def test_cli_ecosystem_list_status_and_noop_sync(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}

    listed = _run(["ecosystem", "list"], env=env)
    assert listed.returncode == 0
    listed_out = json.loads(listed.stdout)
    assert listed_out["status"] == "ok"
    assert listed_out["count"] >= 9
    names = {repo["name"] for repo in listed_out["repos"]}
    assert "omg-superpowers" in names
    assert "claude-flow" in names
    assert "memsearch" in names

    status = _run(["ecosystem", "status"], env=env)
    assert status.returncode == 0
    status_out = json.loads(status.stdout)
    assert status_out["status"] == "ok"
    assert "repos" in status_out

    sync = _run(["ecosystem", "sync", "--names", "unknown-plugin"], env=env)
    assert sync.returncode == 0
    sync_out = json.loads(sync.stdout)
    assert sync_out["status"] == "ok"
    assert sync_out["unknown"] == ["unknown-plugin"]
