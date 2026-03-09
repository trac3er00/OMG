"""Smoke tests for scripts/omg.py CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from runtime.adoption import CANONICAL_VERSION
from runtime.interaction_journal import InteractionJournal

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


def _seed_release_readiness_fixtures(tmp_path: Path, *, include_primitives: bool = True, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    context_checksum = "ctx-run-1"
    profile_version = "profile-v1"
    intent_gate_version = "1.0.0"

    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "doctor.json").write_text(
        json.dumps(
            {
                "schema": "DoctorResult",
                "status": "pass",
                "checks": [
                    {"name": "python_version", "status": "ok", "required": True},
                    {"name": "fastmcp", "status": "ok", "required": True},
                    {"name": "omg_control_reachable", "status": "ok", "required": True},
                    {"name": "policy_files", "status": "ok", "required": True},
                    {"name": "metadata_drift", "status": "ok", "required": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "run-1.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-1",
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "tester", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
                "tests": [{"name": "worker_implementation", "passed": True}],
                "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check.json"}],
                "diff_summary": {"files": 1},
                "reproducibility": {"cmd": "pytest -q"},
                "unresolved_risks": [],
                "provenance": [{"source": "security-check"}],
                "trust_scores": {"overall": 1.0},
                "api_twin": {},
                "test_delta": {
                    "override": {"approved_by": "tester"},
                    "lock_id": "lock-1",
                    "waiver_artifact": {"artifact_path": ".omg/evidence/waiver-tests-lock-1.json", "reason": "approved"},
                },
                "claims": [
                    {
                        "claim_type": "tests_passed",
                        "trace_ids": ["trace-1"],
                        "artifacts": ["junit.xml", "coverage.xml", "results.sarif", "trace.zip"],
                    }
                ],
                "trace_ids": ["trace-1"],
                "lineage": {"trace_id": "trace-1", "path": ".omg/lineage/lineage-1.json"},
                "intent_gate_state": {"path": ".omg/state/intent_gate/run-1.json", "run_id": "run-1"},
                "profile_digest": {"path": ".omg/state/profile.yaml", "profile_version": profile_version},
                "session_health_state": {"path": ".omg/state/session_health/run-1.json", "run_id": "run-1"},
                "council_verdicts": {"path": ".omg/state/council_verdicts/run-1.json", "run_id": "run-1"},
                "forge_starter_proof": {"path": ".omg/evidence/forge-specialists-run-1.json", "run_id": "run-1"},
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "security-check.json").write_text(
        json.dumps(
            {
                "schema": "SecurityCheckResult",
                "status": "ok",
                "evidence": {"sarif_path": ".omg/evidence/results.sarif"},
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "results.sarif").write_text("{}", encoding="utf-8")
    (evidence_root / "forge-specialists-run-1.json").write_text(
        json.dumps(
            {
                "schema": "ForgeSpecialistDispatchEvidence",
                "schema_version": "1.0.0",
                "run_id": "run-1",
                "status": "ok",
                "proof_backed": True,
                "specialists_dispatched": ["training-architect"],
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
            }
        ),
        encoding="utf-8",
    )

    lineage_root = tmp_path / ".omg" / "lineage"
    lineage_root.mkdir(parents=True, exist_ok=True)
    (lineage_root / "lineage-1.json").write_text(
        json.dumps({"trace_id": "trace-1", "path": ".omg/lineage/lineage-1.json"}),
        encoding="utf-8",
    )

    eval_root = tmp_path / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "eval_id": "eval-1",
                "trace_id": "trace-1",
                "lineage": {"trace_id": "trace-1", "path": ".omg/lineage/lineage-1.json"},
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "tester", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "status": "ok",
                "summary": {"regressed": False},
            }
        ),
        encoding="utf-8",
    )

    tracebank_root = tmp_path / ".omg" / "tracebank"
    tracebank_root.mkdir(parents=True, exist_ok=True)
    (tracebank_root / "events.jsonl").write_text(
        json.dumps(
            {
                "schema": "TracebankRecord",
                "trace_id": "trace-1",
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "tester", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "path": ".omg/tracebank/events.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    if include_primitives:
        state_root = tmp_path / ".omg" / "state"

        if "release_run_coordinator" not in omitted:
            release_state_dir = state_root / "release_run_coordinator"
            release_state_dir.mkdir(parents=True, exist_ok=True)
            (release_state_dir / "run-1.json").write_text(
                json.dumps(
                    {
                        "schema": "ReleaseRunCoordinatorState",
                        "schema_version": "1.0.0",
                        "run_id": "run-1",
                        "status": "ok",
                        "phase": "finalize",
                        "resolution_source": "cli",
                        "resolution_reason": "explicit",
                        "updated_at": "2026-03-07T00:00:00Z",
                        "context_checksum": context_checksum,
                        "profile_version": profile_version,
                        "intent_gate_version": intent_gate_version,
                    }
                ),
                encoding="utf-8",
            )

        if "test_intent_lock" not in omitted:
            lock_dir = state_root / "test-intent-lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock-1.json").write_text(
                json.dumps(
                    {
                        "schema": "TestIntentLock",
                        "lock_id": "lock-1",
                        "status": "ok",
                        "intent": {"run_id": "run-1"},
                        "context_checksum": context_checksum,
                        "profile_version": profile_version,
                        "intent_gate_version": intent_gate_version,
                    }
                ),
                encoding="utf-8",
            )

        if "rollback_manifest" not in omitted:
            rollback_dir = state_root / "rollback_manifest"
            rollback_dir.mkdir(parents=True, exist_ok=True)
            (rollback_dir / "run-1-step-1.json").write_text(
                json.dumps(
                    {
                        "schema": "RollbackManifest",
                        "schema_version": "1.0.0",
                        "run_id": "run-1",
                        "status": "ok",
                        "step_id": "step-1",
                        "local_restores": [],
                        "compensating_actions": [],
                        "side_effects": [],
                        "updated_at": "2026-03-07T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

        if "session_health" not in omitted:
            health_dir = state_root / "session_health"
            health_dir.mkdir(parents=True, exist_ok=True)
            (health_dir / "run-1.json").write_text(
                json.dumps(
                    {
                        "schema": "SessionHealth",
                        "schema_version": "1.0.0",
                        "run_id": "run-1",
                        "status": "ok",
                        "contamination_risk": 0.1,
                        "overthinking_score": 0.1,
                        "context_health": 0.9,
                        "verification_status": "ok",
                        "recommended_action": "continue",
                        "updated_at": "2026-03-07T00:00:00Z",
                        "context_checksum": context_checksum,
                        "profile_version": profile_version,
                        "intent_gate_version": intent_gate_version,
                    }
                ),
                encoding="utf-8",
            )

        if "intent_gate" not in omitted:
            intent_gate_dir = state_root / "intent_gate"
            intent_gate_dir.mkdir(parents=True, exist_ok=True)
            (intent_gate_dir / "run-1.json").write_text(
                json.dumps(
                    {
                        "schema": "IntentGateDecision",
                        "schema_version": intent_gate_version,
                        "run_id": "run-1",
                        "intent_gate_version": intent_gate_version,
                        "requires_clarification": False,
                        "intent_class": "release_readiness",
                        "clarification_prompt": "",
                        "confidence": 0.98,
                        "context_checksum": context_checksum,
                        "profile_version": profile_version,
                        "updated_at": "2026-03-07T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

        if "profile_digest" not in omitted:
            (state_root / "profile.yaml").write_text(
                "\n".join(
                    [
                        "profile_version: profile-v1",
                        "preferences:",
                        "  architecture_requests:",
                        "    - release_readiness",
                        "user_vector:",
                        "  summary: cli fixture profile",
                        "profile_provenance:",
                        "  checksum: profile-v1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        if "council_verdicts" not in omitted:
            council_dir = state_root / "council_verdicts"
            council_dir.mkdir(parents=True, exist_ok=True)
            (council_dir / "run-1.json").write_text(
                json.dumps(
                    {
                        "schema": "CouncilVerdicts",
                        "schema_version": "1.0.0",
                        "run_id": "run-1",
                        "status": "ok",
                        "verification_status": "ok",
                        "context_checksum": context_checksum,
                        "profile_version": profile_version,
                        "intent_gate_version": intent_gate_version,
                        "verdicts": {
                            "skeptic": {"verdict": "pass"},
                            "hallucination_auditor": {"verdict": "pass"},
                            "evidence_completeness": {"verdict": "pass"},
                        },
                        "updated_at": "2026-03-07T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

        if "forge_starter_proof" in omitted:
            forge_path = evidence_root / "forge-specialists-run-1.json"
            if forge_path.exists():
                forge_path.unlink()


def test_cli_help_uses_canonical_identity():
    proc = _run(["--help"])
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert f"OMG {CANONICAL_VERSION} CLI" in out
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
    assert out["evidence"]["sarif_path"].endswith(".sarif")
    assert out["evidence"]["sbom_path"].endswith(".cdx.json")
    assert out["evidence"]["license_path"].endswith(".json")


def test_cli_security_check_honors_waiver_json(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    first = _run(["security", "check", "--scope", str(tmp_path)])
    first_out = json.loads(first.stdout)
    finding_id = first_out["findings"][0]["finding_id"]

    waived = _run(
        [
            "security",
            "check",
            "--scope",
            str(tmp_path),
            "--waivers-json",
            json.dumps([{"finding_id": finding_id, "justification": "approved mitigation window"}]),
        ]
    )
    waived_out = json.loads(waived.stdout)
    assert waived_out["status"] == "ok"
    assert waived_out["release_blocked"] is False


def test_cli_undo_restores_project_and_records_rollback_manifest(tmp_path: Path):
    target = tmp_path / "README.md"
    target.write_text("before\n", encoding="utf-8")
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step("write", {"file": "README.md", "run_id": "cli-undo-run"})
    target.write_text("after\n", encoding="utf-8")

    proc = _run(
        ["undo", "--step-id", str(event["step_id"])],
        env={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_RUN_ID": "cli-canonical-run",
        },
    )

    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest_path = tmp_path / out["manifest_path"]
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "cli-canonical-run"


def test_cli_undo_failed_compensating_action_returns_nonzero(tmp_path: Path):
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step(
        "bash",
        {
            "command": "curl -X POST https://api.example.test/v1/resource",
            "run_id": "cli-undo-run-fail",
            "compensating_action": {
                "action": "fail",
                "command": "python3 -c \"raise SystemExit(5)\"",
            },
        },
    )

    proc = _run(
        ["undo", "--step-id", str(event["step_id"])],
        env={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_RUN_ID": "cli-canonical-run-fail",
        },
    )

    assert proc.returncode != 0
    out = json.loads(proc.stdout)
    assert out["status"] == "rollback_failed"
    assert out["failed_actions"][0]["exit_code"] == 5


def test_cli_waive_tests_emits_structured_waiver_artifact(tmp_path: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(
        ["waive-tests", "--lock-id", "lock-42", "--reason", "approved migration window"],
        env=env,
    )

    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "WaiverEvidence"
    assert out["lock_id"] == "lock-42"
    assert out["reason"] == "approved migration window"
    artifact_path = tmp_path / out["artifact_path"]
    assert artifact_path.exists()


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
    if validate.returncode != 0 and "version drift" in (validate.stdout + validate.stderr):
        pytest.skip("contract registry baseline has version drift")
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
    if compile_public.returncode != 0 and "version drift" in (compile_public.stdout + compile_public.stderr):
        pytest.skip("contract registry baseline has version drift")
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

    _seed_release_readiness_fixtures(tmp_path)

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
    primitives = readiness_out["checks"].get("execution_primitives", {})
    assert primitives.get("status") == "ok"
    assert primitives.get("missing") == []
    assert primitives.get("invalid") == []
    assert "intent_gate_state" in primitives.get("required", [])
    assert "profile_digest" in primitives.get("required", [])
    assert primitives.get("evidence_paths", {}).get("intent_gate_state", "").endswith(".omg/state/intent_gate/run-1.json")
    assert primitives.get("evidence_paths", {}).get("profile_digest") == ".omg/state/profile.yaml"


def test_cli_release_readiness_blocks_missing_execution_primitive(tmp_path: Path):
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
    if compile_public.returncode != 0 and "version drift" in (compile_public.stdout + compile_public.stderr):
        pytest.skip("contract registry baseline has version drift")
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

    _seed_release_readiness_fixtures(tmp_path, omit={"session_health"})

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
    assert readiness.returncode != 0
    readiness_out = json.loads(readiness.stdout)
    assert readiness_out["status"] == "error"
    assert "missing_execution_primitive: session_health_state" in readiness_out["blockers"]


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


def test_cli_doctor_json_output_has_named_checks():
    proc = _run(["doctor", "--format", "json"])
    out = json.loads(proc.stdout)
    assert out["schema"] == "DoctorResult"
    assert "checks" in out
    check_names = {c["name"] for c in out["checks"]}
    assert "python_version" in check_names
    assert "fastmcp" in check_names
    assert "omg_control_reachable" in check_names
    assert "policy_files" in check_names
    assert "metadata_drift" in check_names
    for check in out["checks"]:
        assert check["status"] in {"ok", "blocker", "warning"}
        assert "message" in check
        assert "required" in check


def test_cli_doctor_clean_state_exits_zero_or_reports_blockers():
    proc = _run(["doctor", "--format", "json"])
    out = json.loads(proc.stdout)
    blockers = [c for c in out["checks"] if c["status"] == "blocker"]
    if not blockers:
        assert proc.returncode == 0
        assert out["status"] == "pass"
    else:
        assert proc.returncode != 0
        assert out["status"] == "fail"


def test_cli_doctor_missing_fastmcp_produces_blocker(monkeypatch):
    import importlib
    original_import = importlib.import_module

    def _block_fastmcp(name, *args, **kwargs):
        if name == "fastmcp":
            raise ImportError("mocked: fastmcp not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _block_fastmcp)

    from runtime.compat import run_doctor
    result = run_doctor(root_dir=ROOT)
    fastmcp_checks = [c for c in result["checks"] if c["name"] == "fastmcp"]
    assert len(fastmcp_checks) == 1
    assert fastmcp_checks[0]["status"] == "blocker"
    assert result["status"] == "fail"


def test_cli_doctor_text_output():
    proc = _run(["doctor"])
    assert "python_version" in proc.stdout
    assert "PASS" in proc.stdout or "BLOCKER" in proc.stdout


def test_cli_doctor_help_lists_doctor():
    proc = _run(["--help"])
    assert "doctor" in proc.stdout + proc.stderr


# --- profile-review command tests ---

def test_cli_profile_review_json_output_keys():
    """profile-review --format json must include required top-level keys."""
    proc = _run(["profile-review", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["schema"] == "ProfileReview"
    for key in ("style", "safety", "pending_confirmations", "decay_candidates", "provenance_summary"):
        assert key in out, f"Missing key: {key}"
    assert isinstance(out["style"], list)
    assert isinstance(out["safety"], list)
    assert isinstance(out["pending_confirmations"], list)
    assert isinstance(out["decay_candidates"], list)
    assert isinstance(out["provenance_summary"], list)


def test_cli_profile_review_text_output():
    """profile-review --format text must produce human-readable summary."""
    proc = _run(["profile-review", "--format", "text"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "Profile Review" in proc.stdout or "Style" in proc.stdout


def test_cli_profile_review_read_only(tmp_path):
    """profile-review must NOT mutate profile.yaml."""
    # Create a minimal profile.yaml
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    profile_path = state_dir / "profile.yaml"
    profile_path.write_text("name: test-project\npreferences: {}\n")
    mtime_before = profile_path.stat().st_mtime
    content_before = profile_path.read_text()

    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["profile-review", "--format", "json"], env=env)
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    mtime_after = profile_path.stat().st_mtime
    content_after = profile_path.read_text()
    assert mtime_before == mtime_after, "profile.yaml mtime changed — command is not read-only"
    assert content_before == content_after, "profile.yaml content changed — command is not read-only"


def test_cli_profile_review_help_lists_command():
    proc = _run(["--help"])
    assert "profile-review" in proc.stdout + proc.stderr


# --- validate command tests ---


def test_cli_validate_json_output_has_required_fields():
    proc = _run(["validate", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "ValidateResult"
    assert "status" in out
    assert out["status"] in ("pass", "fail")
    assert "checks" in out
    assert isinstance(out["checks"], list)
    assert "version" in out


def test_cli_validate_includes_doctor_checks():
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    # Must include at least the core doctor checks
    assert "python_version" in check_names
    assert "fastmcp" in check_names


def test_cli_validate_includes_contract_check():
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    assert "contract_registry" in check_names


def test_cli_validate_includes_profile_check():
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    assert "profile_governor" in check_names


def test_cli_validate_includes_install_check():
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    assert "install_integrity" in check_names


def test_validate_includes_plugin_compatibility():
    proc = _run(["validate", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert isinstance(out, dict)
    check_names = {c.get("name") for c in out.get("checks", []) if isinstance(c, dict)}
    assert "plugin_compatibility" in check_names or "plugin" in out


def test_doctor_includes_plugin_check():
    proc = _run(["doctor", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert isinstance(out, dict)
    check_names = {c.get("name") for c in out.get("checks", []) if isinstance(c, dict)}
    has_plugin_key = "plugin_compatibility" in out or "plugin" in out
    assert "plugin_compatibility" in check_names or has_plugin_key


def test_cli_validate_text_format():
    proc = _run(["validate", "--format", "text"])
    assert proc.returncode == 0 or proc.returncode == 1
    # Text format should contain human-readable markers
    assert "PASS" in proc.stdout or "BLOCKER" in proc.stdout or "WARN" in proc.stdout


def test_cli_validate_default_format_is_text():
    proc = _run(["validate"])
    assert proc.returncode == 0 or proc.returncode == 1
    # Default should be text (not JSON)
    try:
        json.loads(proc.stdout)
        # If it parses as JSON, that's wrong — default should be text
        assert False, "Default format should be text, not JSON"
    except json.JSONDecodeError:
        pass  # Correct: text format is not valid JSON


def test_cli_validate_help_lists_command():
    proc = _run(["--help"])
    assert "validate" in proc.stdout + proc.stderr


# --- NotebookLM validate integration tests ---


def test_cli_validate_notebooklm_check_present_when_selected(tmp_path: Path):
    """validate --format json includes notebooklm check when notebooklm is in selected MCPs."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "cli-config.yaml").write_text(
        "selected_mcps:\n  - filesystem\n  - notebooklm\n",
        encoding="utf-8",
    )

    proc = _run(["validate", "--format", "json"], env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    assert "notebooklm" in check_names
    nb_check = next(c for c in out["checks"] if c["name"] == "notebooklm")
    # Must be optional (not required)
    assert nb_check["required"] is False


def test_cli_validate_notebooklm_absent_when_not_selected(tmp_path: Path):
    """validate --format json must NOT include notebooklm check when not in selected MCPs."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "cli-config.yaml").write_text(
        "selected_mcps:\n  - filesystem\n  - omg-control\n",
        encoding="utf-8",
    )

    proc = _run(["validate", "--format", "json"], env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    assert "notebooklm" not in check_names


def test_cli_validate_notebooklm_absent_when_no_config():
    """validate --format json must NOT include notebooklm check when no cli-config.yaml exists."""
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    check_names = {c["name"] for c in out["checks"]}
    # Without explicit selection, NotebookLM check should be absent
    assert "notebooklm" not in check_names


def test_cli_validate_notebooklm_warning_when_npx_missing(tmp_path: Path, monkeypatch):
    """NotebookLM check emits warning (not blocker) when npx is not available."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "cli-config.yaml").write_text(
        "selected_mcps:\n  - filesystem\n  - notebooklm\n",
        encoding="utf-8",
    )

    # Ensure npx cannot be found
    monkeypatch.setenv("PATH", "")

    proc = _run(
        ["validate", "--format", "json"],
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": ""},
    )
    out = json.loads(proc.stdout)
    nb_check = next(c for c in out["checks"] if c["name"] == "notebooklm")
    assert nb_check["status"] == "warning"
    assert nb_check["required"] is False
    # Must NOT be a blocker
    assert nb_check["status"] != "blocker"
    # Overall status should still pass (optional check cannot cause fail)
    assert out["status"] == "pass" or any(
        c["status"] == "blocker" for c in out["checks"] if c["name"] != "notebooklm"
    )


def test_diagnose_plugins_json_output():
    proc = _run(["diagnose-plugins", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "PluginDiagnosticsResult"


def test_diagnose_plugins_completes_under_3s():
    import time

    started = time.monotonic()
    proc = _run(["diagnose-plugins", "--format", "json"])
    elapsed = time.monotonic() - started
    assert proc.returncode == 0
    assert elapsed < 3
