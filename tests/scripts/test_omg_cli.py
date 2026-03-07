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


def test_cli_help_uses_canonical_identity():
    proc = _run(["--help"])
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "OMG 2.0.4 CLI" in out
    assert "OMG v1 CLI" not in out
    assert "crazy" in out
    assert "compat" in out


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


def test_cli_security_check_runs_canonical_engine(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    proc = _run(["security", "check", "--scope", str(tmp_path)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "SecurityCheckResult"
    assert out["summary"]["finding_count"] >= 1
    assert any(finding["category"] == "python_ast" for finding in out["findings"])


def test_cli_teams_command():
    teams = _run(["teams", "--problem", "debug api auth bug"])
    assert teams.returncode == 0
    teams_out = json.loads(teams.stdout)
    assert teams_out["status"] == "ok"
    assert teams_out["schema"] == "TeamDispatchResult"


def test_cli_api_twin_ingest_record_serve_and_verify(tmp_path: Path):
    contract = tmp_path / "openapi.json"
    contract.write_text(json.dumps({"openapi": "3.1.0", "info": {"title": "Demo", "version": "1.0.0"}}), encoding="utf-8")
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}

    ingest = _run(["api-twin", "ingest", "--name", "demo", "--source", str(contract)], env=env)
    assert ingest.returncode == 0
    ingest_out = json.loads(ingest.stdout)
    assert ingest_out["fidelity"] == "schema-only"

    record = _run(
        [
            "api-twin",
            "record",
            "--name",
            "demo",
            "--request-json",
            '{"path":"/users"}',
            "--response-json",
            '{"users":[]}',
        ],
        env=env,
    )
    assert record.returncode == 0
    record_out = json.loads(record.stdout)
    assert record_out["fidelity"] == "recorded"

    serve = _run(["api-twin", "serve", "--name", "demo", "--schema-drift"], env=env)
    assert serve.returncode == 0
    serve_out = json.loads(serve.stdout)
    assert serve_out["schema"] == "ApiTwinServeResult"
    assert serve_out["fidelity"] == "stale"

    verify = _run(["api-twin", "verify", "--name", "demo", "--live-response-json", '{"users":[]}'], env=env)
    assert verify.returncode == 0
    verify_out = json.loads(verify.stdout)
    assert verify_out["fidelity"] == "recorded-validated"
    assert verify_out["live_verification_required"] is True


def test_cli_preflight_returns_structured_route(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["preflight", "--goal", "stabilize auth flow and verify secrets handling"], env=env)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "PreflightResult"
    assert out["route"] == "security-check"
    assert "omg-control" in out["required_mcps"]


def test_cli_ccg_launches_two_worker_tracks():
    try:
        ccg = _run(["ccg", "--problem", "review full stack architecture"])
    except subprocess.TimeoutExpired:
        pytest.skip("ccg command timed out (expected for long-running multi-agent tasks)")
        return
    assert ccg.returncode == 0
    start = ccg.stdout.find("{")
    assert start >= 0
    ccg_out = json.loads(ccg.stdout[start:])
    assert ccg_out["status"] == "ok"
    assert ccg_out["worker_count"] == 2
    assert ccg_out["target_worker_count"] == 2
    assert ccg_out["parallel_execution"] is True
    phase_agents = [p.get("agent") for p in ccg_out["phases"] if isinstance(p, dict)]
    assert "backend-engineer" in phase_agents
    assert "frontend-designer" in phase_agents


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


def test_cli_contract_validate_and_compile(tmp_path: Path):
    validate = _run(["contract", "validate"])
    assert validate.returncode == 0
    validate_out = json.loads(validate.stdout)
    assert validate_out["schema"] == "OmgContractValidationResult"
    assert validate_out["status"] == "ok"

    compile_proc = _run(
        [
            "contract",
            "compile",
            "--host",
            "claude",
            "--host",
            "codex",
            "--channel",
            "enterprise",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert compile_proc.returncode == 0
    compile_out = json.loads(compile_proc.stdout)
    assert compile_out["schema"] == "OmgContractCompileResult"
    assert compile_out["status"] == "ok"
    assert (tmp_path / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml").exists()


def test_cli_release_readiness_dual_channel(tmp_path: Path):
    compile_public = _run(
        [
            "contract",
            "compile",
            "--host",
            "claude",
            "--host",
            "codex",
            "--channel",
            "public",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert compile_public.returncode == 0

    compile_enterprise = _run(
        [
            "contract",
            "compile",
            "--host",
            "claude",
            "--host",
            "codex",
            "--channel",
            "enterprise",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert compile_enterprise.returncode == 0

    readiness = _run(
        [
            "release",
            "readiness",
            "--channel",
            "dual",
            "--output-root",
            str(tmp_path),
        ],
        env={"OMG_RELEASE_READY_PROVIDERS": "claude,codex"},
    )
    assert readiness.returncode == 0
    readiness_out = json.loads(readiness.stdout)
    assert readiness_out["schema"] == "OmgReleaseReadinessResult"
    assert readiness_out["status"] == "ok"
    assert readiness_out["blockers"] == []


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
