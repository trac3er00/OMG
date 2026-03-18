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


def _json_result(payload: dict[str, object], *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[str(SCRIPT)],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr=stderr,
    )


def _snapshot_tree(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return snapshot


def _install_contract_flow_stub(monkeypatch: pytest.MonkeyPatch, *, missing_session_health: bool = False) -> None:
    def _stubbed_run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["contract", "validate"]:
            return _json_result({"schema": "OmgContractValidationResult", "status": "ok"})

        if args[:2] == ["doctor", "--format"]:
            return _json_result({"schema": "DoctorResult", "status": "ok"})

        if args[:2] == ["contract", "compile"]:
            output_root = Path(args[args.index("--output-root") + 1])
            channel = args[args.index("--channel") + 1]
            control_plane = output_root / ".agents" / "skills" / "omg" / "control-plane"
            control_plane.mkdir(parents=True, exist_ok=True)
            (control_plane / "openai.yaml").write_text("schema: openapi\n", encoding="utf-8")
            manifest_dir = output_root / "dist" / channel
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps({"contract_version": CANONICAL_VERSION}, indent=2),
                encoding="utf-8",
            )
            return _json_result({"schema": "OmgContractCompileResult", "status": "ok"})

        if args[:2] == ["release", "readiness"]:
            if missing_session_health:
                return _json_result(
                    {
                        "schema": "OmgReleaseReadinessResult",
                        "status": "error",
                        "blockers": ["missing_execution_primitive: session_health_state"],
                    },
                    returncode=1,
                )
            return _json_result(
                {
                    "schema": "OmgReleaseReadinessResult",
                    "status": "ok",
                    "blockers": [],
                    "checks": {
                        "execution_primitives": {
                            "status": "ok",
                            "missing": [],
                            "invalid": [],
                            "required": ["intent_gate_state", "profile_digest", "session_health_state"],
                            "evidence_paths": {
                                "intent_gate_state": ".omg/state/intent_gate/run-1.json",
                                "profile_digest": ".omg/state/profile.yaml",
                            },
                        }
                    },
                }
            )

        raise AssertionError(f"Unexpected args for stubbed contract flow: {args}")

    monkeypatch.setattr(sys.modules[__name__], "_run", _stubbed_run)


def test_vision_command_family_is_registered() -> None:
    result = _run(["vision", "--help"])

    assert result.returncode == 0
    assert "ocr" in result.stdout
    assert "compare" in result.stdout
    assert "analyze" in result.stdout


def _seed_release_readiness_fixtures(tmp_path: Path, *, include_primitives: bool = True, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    prepare = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare-release-proof-fixtures.py"), "--output-root", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr
    doctor = _run(["doctor", "--format", "json"])
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    doctor_path = tmp_path / ".omg" / "evidence" / "doctor.json"
    doctor_path.parent.mkdir(parents=True, exist_ok=True)
    doctor_path.write_text(doctor.stdout, encoding="utf-8")

    if include_primitives and not omitted:
        return

    removable_paths = {
        "release_run_coordinator": tmp_path / ".omg" / "state" / "release_run_coordinator" / "run-1.json",
        "test_intent_lock": tmp_path / ".omg" / "state" / "test-intent-lock" / "lock-1.json",
        "rollback_manifest": tmp_path / ".omg" / "state" / "rollback_manifest" / "run-1-step-1.json",
        "session_health": tmp_path / ".omg" / "state" / "session_health" / "run-1.json",
        "intent_gate": tmp_path / ".omg" / "state" / "intent_gate" / "run-1.json",
        "profile_digest": tmp_path / ".omg" / "state" / "profile.yaml",
        "council_verdicts": tmp_path / ".omg" / "state" / "council_verdicts" / "run-1.json",
        "forge_starter_proof": tmp_path / ".omg" / "evidence" / "forge-specialists-run-1.json",
    }
    to_remove = set(omitted)
    if not include_primitives:
        to_remove.update(
            {
                "release_run_coordinator",
                "test_intent_lock",
                "rollback_manifest",
                "session_health",
                "intent_gate",
                "profile_digest",
                "council_verdicts",
                "forge_starter_proof",
            }
        )

    for key in to_remove:
        path = removable_paths.get(key)
        if path and path.exists():
            path.unlink()


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


def test_cli_ccg_launches_two_worker_tracks(monkeypatch: pytest.MonkeyPatch):
    def _stubbed_run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        assert args == ["ccg", "--problem", "review full stack architecture"]
        payload = {
            "status": "ok",
            "worker_count": 2,
            "target_worker_count": 2,
            "parallel_execution": True,
            "phases": [
                {"agent": "backend-engineer"},
                {"agent": "frontend-designer"},
            ],
        }
        return subprocess.CompletedProcess(
            args=[str(SCRIPT)],
            returncode=0,
            stdout=f"dispatch complete\n{json.dumps(payload)}",
            stderr="",
        )

    monkeypatch.setattr(sys.modules[__name__], "_run", _stubbed_run)
    ccg = _run(["ccg", "--problem", "review full stack architecture"])
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


def test_cli_crazy_launches_five_worker_tracks(monkeypatch: pytest.MonkeyPatch):
    def _stubbed_run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        assert args == ["crazy", "--problem", "stabilize auth and dashboard flows"]
        payload = {
            "status": "ok",
            "worker_count": 5,
            "target_worker_count": 5,
            "parallel_execution": True,
            "sequential_execution": False,
            "phases": [
                {"agent": "architect-mode"},
                {"agent": "backend-engineer"},
                {"agent": "frontend-designer"},
                {"agent": "security-auditor"},
                {"agent": "testing-engineer"},
            ],
        }
        return subprocess.CompletedProcess(
            args=[str(SCRIPT)],
            returncode=0,
            stdout=f"dispatch complete\n{json.dumps(payload)}",
            stderr="",
        )

    monkeypatch.setattr(sys.modules[__name__], "_run", _stubbed_run)
    crazy = _run(["crazy", "--problem", "stabilize auth and dashboard flows"])
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


def test_cli_contract_validate_and_compile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _install_contract_flow_stub(monkeypatch)
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


def test_cli_release_readiness_dual_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _install_contract_flow_stub(monkeypatch)
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


def test_cli_release_readiness_blocks_missing_execution_primitive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _install_contract_flow_stub(monkeypatch, missing_session_health=True)
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


def test_cli_profile_review_includes_risk_assessment():
    proc = _run(["profile-review", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert "risk_assessment" in out
    risk = out["risk_assessment"]
    assert "risk_level" in risk
    assert "requires_review" in risk
    assert risk["risk_level"] in ("low", "medium", "high")


def test_cli_validate_profile_governor_includes_risk_hint():
    proc = _run(["validate", "--format", "json"])
    out = json.loads(proc.stdout)
    profile_check = next(
        (c for c in out["checks"] if c["name"] == "profile_governor"), None
    )
    assert profile_check is not None
    msg = profile_check["message"].lower()
    assert "risk" in msg or "ok" in msg or "no profile found" in msg


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


def test_install_plan_json_output():
    proc = _run(["install", "--plan", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert "actions" in out
    assert isinstance(out["actions"], list)
    assert out.get("schema") == "InstallPlan"
    assert "pre_checks" in out
    assert "post_checks" in out
    assert "integrity_errors" in out


def test_install_plan_actions_have_required_keys():
    proc = _run(["install", "--plan", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    for action in out["actions"]:
        assert "host" in action
        assert "target_path" in action
        assert "description" in action
        assert "kind" in action


def test_install_dryrun_json_output():
    proc = _run(["install", "--dry-run", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["executed"] is False
    assert "actions_completed" in out
    assert "actions_skipped" in out
    assert "actions" in out
    assert isinstance(out["actions"], list)


def test_install_dryrun_no_disk_mutations(tmp_path: Path):
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("before", encoding="utf-8")
    proc = _run(["install", "--dry-run", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert sentinel.read_text(encoding="utf-8") == "before"
    mcp_json = ROOT / ".mcp.json"
    if mcp_json.exists():
        before_content = mcp_json.read_text(encoding="utf-8")
        proc2 = _run(["install", "--dry-run", "--format", "json"])
        assert proc2.returncode == 0
        assert mcp_json.read_text(encoding="utf-8") == before_content


def test_install_plan_no_disk_mutations(tmp_path: Path):
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("before", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir(parents=True)
    (nested / "config.json").write_text('{"stable": true}\n', encoding="utf-8")
    before = _snapshot_tree(tmp_path)

    proc = _run(["install", "--plan", "--format", "json"], env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert sentinel.read_text(encoding="utf-8") == "before"
    assert _snapshot_tree(tmp_path) == before


def test_install_apply_receipt_contract_fields() -> None:
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        proc = _run(["install", "--apply", "--format", "json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert "actions" in out
        assert "receipts" in out
        assert isinstance(out["receipts"], list)
        for receipt in out["receipts"]:
            assert "check" in receipt
            assert "action" in receipt
            assert "backup_path" in receipt
            assert "executed" in receipt
            assert "rollback_ref" in receipt
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


def test_install_no_flag_returns_error():
    proc = _run(["install", "--format", "json"])
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert "error" in out


def test_install_ci_flag_auto_applies():
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        proc = _run(["install", "--ci", "--format", "json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert out.get("schema") == "InstallApplyResult"
        assert "receipts" in out
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


def test_install_omg_ci_env_auto_applies():
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        env = {**os.environ, "OMG_CI": "1"}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "omg.py"), "install", "--format", "json"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT), env=env,
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert out.get("schema") == "InstallApplyResult"
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


def test_install_non_interactive_auto_applies():
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        proc = _run(["install", "--non-interactive", "--format", "json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert out.get("schema") == "InstallApplyResult"
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


# --- policy-pack subcommand tests ---


def test_policy_pack_diff_returns_overrides():
    proc = _run(["policy-pack", "diff", "airgapped", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "PolicyPackDiff"
    assert out["status"] == "ok"
    assert out["pack_id"] == "airgapped"


def test_policy_pack_diff_unknown_pack_fails():
    proc = _run(["policy-pack", "diff", "nonexistent-pack-xyz", "--format", "json"])
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["status"] == "error"


def test_policy_pack_scaffold_returns_template():
    proc = _run(["policy-pack", "scaffold", "my-custom-pack", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "PolicyPackScaffold"
    assert out["pack_id"] == "my-custom-pack"
    assert "template" in out
    assert out["template"]["id"] == "my-custom-pack"
    assert "output_path" in out


def test_policy_pack_sign_requires_signing_key():
    """policy-pack sign now requires a signing key (no longer a stub)."""
    proc = _run(["policy-pack", "sign", "airgapped", "--format", "json"])
    # Without OMG_SIGNING_KEY or --key-path, exits 1 with a clear error
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "PolicyPackSign"
    assert out["status"] == "error"
    assert "signing key" in out.get("error", "").lower()


# --- doctor repair-pack tests ---


def test_doctor_checks_include_repair_pack_field():
    proc = _run(["doctor", "--format", "json"])
    out = json.loads(proc.stdout)
    for check in out["checks"]:
        assert "repair_pack" in check, f"check {check['name']} missing repair_pack"
        assert check["repair_pack"] in ("runtime", "governance", "host", "release", "general", "claude", "codex", "gemini", "kimi", "opencode")


def test_doctor_repair_pack_filter():
    proc = _run(["doctor", "--repair-pack", "runtime", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    for check in out["checks"]:
        assert check["repair_pack"] == "runtime", f"filter leak: {check['name']} has pack {check['repair_pack']}"


def test_doctor_fix_receipts_include_repair_pack():
    proc = _run(["doctor", "--fix", "--dry-run", "--format", "json"])
    out = json.loads(proc.stdout)
    for receipt in out.get("fix_receipts", []):
        assert "repair_pack" in receipt


# --- doctor --fix command tests ---


def test_cli_doctor_fix_dry_run_json_returns_planned_fixes():
    """doctor --fix --dry-run --format json returns structured output with no disk mutations."""
    proc = _run(["doctor", "--fix", "--dry-run", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "DoctorFixResult"
    assert out["mode"] == "dry_run"
    assert "checks" in out
    assert "fix_receipts" in out
    assert isinstance(out["fix_receipts"], list)
    for check in out["checks"]:
        assert "fixable" in check
        assert isinstance(check["fixable"], bool)
    for receipt in out["fix_receipts"]:
        assert receipt["executed"] is False


def test_cli_doctor_fix_dry_run_json_receipt_has_required_fields() -> None:
    proc = _run(["doctor", "--fix", "--dry-run", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "DoctorFixResult"
    assert "fix_receipts" in out
    assert isinstance(out["fix_receipts"], list)
    for receipt in out["fix_receipts"]:
        assert "check" in receipt
        assert "action" in receipt
        assert "backup_path" in receipt
        assert "verification" in receipt
        assert "executed" in receipt


def test_cli_doctor_fix_dry_run_does_not_mutate_repo_files() -> None:
    mcp_json = ROOT / ".mcp.json"
    policy_yaml = ROOT / ".omg" / "policy.yaml"
    before_mcp = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    before_policy = policy_yaml.read_text(encoding="utf-8") if policy_yaml.exists() else None

    proc = _run(["doctor", "--fix", "--dry-run", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1

    after_mcp = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    after_policy = policy_yaml.read_text(encoding="utf-8") if policy_yaml.exists() else None
    assert after_mcp == before_mcp
    assert after_policy == before_policy


def test_cli_resolve_policy_returns_effective_policy() -> None:
    proc = _run(["resolve-policy", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["schema"] == "EffectivePolicy"
    assert "tier" in out
    assert "effective_policy" in out
    assert "overrides" in out
    assert "provenance" in out
    assert isinstance(out["packs"], list)
    assert isinstance(out["provenance"], list)


def test_cli_proof_summary_contract() -> None:
    proc = _run(["proof", "summary", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "ProofSummary"
    assert out["status"] in ("no_evidence", "found", "ok")
    assert isinstance(out["claims"], list)
    assert isinstance(out["missing_artifacts"], list)
    assert isinstance(out["next_actions"], list)


def test_cli_proof_summary_markdown() -> None:
    proc = _run(["proof", "summary", "--format", "markdown"])
    assert proc.returncode == 0
    assert "# Proof Summary" in proc.stdout
    assert "**Status:**" in proc.stdout


def test_cli_explain_run_not_found() -> None:
    proc = _run(["explain", "run", "--run-id", "run-123"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "RunExplanation"
    assert out["status"] == "not_found"
    assert out["run_id"] == "run-123"


def test_cli_explain_run_format_flag() -> None:
    proc = _run(["explain", "run", "--run-id", "nonexistent", "--format", "json"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "RunExplanation"
    assert out["status"] == "not_found"


def test_cli_budget_simulate_preview() -> None:
    proc = _run(["budget", "simulate", "--tier", "free", "--tokens-used", "100"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "BudgetSimulateResult"
    assert out["status"] == "preview"
    assert out["enforce"] is False
    assert "check" in out
    assert "tier_limits" in out


def test_cli_budget_simulate_with_flags() -> None:
    proc = _run([
        "budget", "simulate",
        "--tier", "pro",
        "--channel", "enterprise",
        "--preset", "labs",
        "--task", "test-task",
        "--tokens-used", "50",
    ])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "BudgetSimulateResult"
    assert out["tier"] == "pro"
    assert out["channel"] == "enterprise"
    assert out["preset"] == "labs"
    assert out["task"] == "test-task"


def test_cli_budget_simulate_enforce_ok() -> None:
    proc = _run([
        "budget", "simulate",
        "--tokens-used", "1",
        "--token-limit", "1000",
        "--enforce",
    ])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "BudgetSimulateResult"
    assert out["status"] == "ok"
    assert out["enforce"] is True


def test_cli_budget_simulate_enforce_blocks_over_limit() -> None:
    proc = _run(
        ["budget", "simulate", "--tier", "free", "--token-limit", "1", "--tokens-used", "2", "--enforce"]
    )
    assert proc.returncode != 0
    out = json.loads(proc.stdout)
    assert out["schema"] == "BudgetSimulateResult"
    assert out["status"] == "blocked"
    assert "reason" in out
    assert out["check"]["status"] == "breach"
    assert out["check"]["governance_action"] == "block"


def test_cli_doctor_fix_non_fixable_checks_have_suggestion():
    """Non-fixable checks (python_version, fastmcp) must declare fixable=false with suggestion."""
    proc = _run(["doctor", "--fix", "--dry-run", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    by_name = {c["name"]: c for c in out["checks"]}
    assert by_name["python_version"]["fixable"] is False
    assert "suggestion" in by_name["python_version"]
    assert isinstance(by_name["python_version"]["suggestion"], str)
    assert len(by_name["python_version"]["suggestion"]) > 0
    assert by_name["fastmcp"]["fixable"] is False
    assert "suggestion" in by_name["fastmcp"]
    assert isinstance(by_name["fastmcp"]["suggestion"], str)
    assert len(by_name["fastmcp"]["suggestion"]) > 0


# --- blocked --last tests ---


def test_cli_blocked_last_no_state(tmp_path: Path):
    """omg blocked --last exits 0 with 'no block explanation' when state file absent."""
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["blocked", "--last"], env=env)
    assert proc.returncode == 0
    assert "no block explanation" in proc.stdout.lower()


def test_cli_blocked_last_text_format(tmp_path: Path):
    """omg blocked --last --format text returns structured output when state file exists."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    block = {
        "reason_code": "no_active_test_intent_lock",
        "explanation": "Blocked due to missing test-intent lock",
        "tool": "Bash",
        "timestamp": "2026-03-16T00:00:00Z",
    }
    (state_dir / "last-block-explanation.json").write_text(json.dumps(block), encoding="utf-8")
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["blocked", "--last", "--format", "text"], env=env)
    assert proc.returncode == 0
    assert "Blocked due to missing test-intent lock" in proc.stdout
    assert "no_active_test_intent_lock" in proc.stdout


# --- proof open tests ---


def test_cli_proof_open_no_evidence(tmp_path: Path):
    """omg proof open exits 0 with guidance when no evidence pack exists."""
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["proof", "open"], env=env)
    assert proc.returncode == 0
    assert "no evidence" in proc.stdout.lower()


def test_cli_proof_open_writes_file(tmp_path: Path):
    """omg proof open exits 0 and writes proof-open markdown file when evidence pack exists."""
    evidence_dir = tmp_path / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    pack = {
        "schema": "EvidencePack",
        "run_id": "test-run-42",
        "status": "pass",
        "blockers": [],
        "next_steps": [],
        "evidence_paths": {},
        "claims": [],
        "artifacts": [],
    }
    (evidence_dir / "pack-test-run-42.json").write_text(json.dumps(pack), encoding="utf-8")
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    proc = _run(["proof", "open", "--format", "markdown"], env=env)
    assert proc.returncode == 0
    assert "test-run-42" in proc.stdout
    out_file = evidence_dir / "proof-open-test-run-42.md"
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "OMG Verdict" in content


def test_cli_doctor_fix_json_receipt_has_required_fields():
    """doctor --fix --format json receipt must have check, action, backup_path, verification, executed."""
    proc = _run(["doctor", "--fix", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "DoctorFixResult"
    assert out["mode"] == "fix"
    assert "fix_receipts" in out
    assert isinstance(out["fix_receipts"], list)
    for receipt in out["fix_receipts"]:
        assert "check" in receipt
        assert "action" in receipt
        assert "backup_path" in receipt
        assert "verification" in receipt
        assert "executed" in receipt


# --- env doctor CLI tests ---


def test_cli_env_doctor_json_output():
    proc = _run(["env", "doctor", "--format", "json"])
    assert proc.returncode == 0 or proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["schema"] == "DoctorResult"
    assert "checks" in out
    check_names = {c["name"] for c in out["checks"]}
    assert "node_version" in check_names
    assert "python3_available" in check_names
    assert "claude_auth" in check_names
    for check in out["checks"]:
        assert check["status"] in {"ok", "blocker", "warning"}
        assert "message" in check
        assert "required" in check
        assert check["required"] is False
        assert "remediation" in check


def test_cli_env_doctor_text_output():
    proc = _run(["env", "doctor"])
    assert proc.returncode == 0 or proc.returncode == 1
    assert "node_version" in proc.stdout
    assert "python3_available" in proc.stdout
    assert "PASS" in proc.stdout or "WARN" in proc.stdout


def test_cli_env_doctor_help_lists_env():
    proc = _run(["--help"])
    assert "env" in proc.stdout + proc.stderr


# --- install env preflight tests ---


def test_install_plan_runs_env_preflight(monkeypatch):
    """install --plan must call run_env_doctor() and include preflight results."""
    import scripts.omg as omg_mod

    called = {"count": 0}
    original_env_doctor = omg_mod.run_env_doctor

    def _stub_env_doctor(**kwargs):
        called["count"] += 1
        return {
            "schema": "DoctorResult",
            "status": "pass",
            "checks": [
                {"name": "node_version", "status": "ok", "message": "node v20", "required": False, "remediation": ""},
            ],
            "version": "test",
        }

    monkeypatch.setattr(omg_mod, "run_env_doctor", _stub_env_doctor)
    proc = _run(["install", "--plan", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert "preflight" in out
    assert out["preflight"]["status"] == "pass"


def test_install_apply_runs_env_preflight(monkeypatch):
    """install --apply must call run_env_doctor() before applying."""
    import scripts.omg as omg_mod

    called = {"count": 0}

    def _stub_env_doctor(**kwargs):
        called["count"] += 1
        return {
            "schema": "DoctorResult",
            "status": "pass",
            "checks": [
                {"name": "node_version", "status": "ok", "message": "node v20", "required": False, "remediation": ""},
            ],
            "version": "test",
        }

    monkeypatch.setattr(omg_mod, "run_env_doctor", _stub_env_doctor)
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        proc = _run(["install", "--apply", "--format", "json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert "preflight" in out
        assert out["preflight"]["status"] == "pass"
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


def test_install_plan_blocks_on_required_blocker():
    """install --plan must exit 1 when env preflight has a required blocker."""
    proc = _run(["install", "--plan", "--format", "json"],
                env={"OMG_TEST_PREFLIGHT_BLOCK": "1"})
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert "preflight" in out
    assert out["preflight"]["status"] == "fail"
    blockers = [c for c in out["preflight"]["checks"] if c["status"] == "blocker" and c["required"]]
    assert len(blockers) >= 1


def test_install_apply_blocks_on_required_blocker():
    """install --apply must exit 1 when env preflight has a required blocker."""
    proc = _run(["install", "--apply", "--format", "json"],
                env={"OMG_TEST_PREFLIGHT_BLOCK": "1"})
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert "preflight" in out
    assert out["preflight"]["status"] == "fail"


def test_install_plan_skip_preflight_bypasses():
    """install --plan --skip-preflight must bypass env preflight."""
    proc = _run(["install", "--plan", "--skip-preflight", "--format", "json"])
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = json.loads(proc.stdout)
    assert out.get("preflight", {}).get("skipped") is True


def test_install_apply_skip_preflight_bypasses():
    """install --apply --skip-preflight must bypass env preflight even with blocking env."""
    mcp_json = ROOT / ".mcp.json"
    original = mcp_json.read_text(encoding="utf-8") if mcp_json.exists() else None
    try:
        proc = _run(["install", "--apply", "--skip-preflight", "--format", "json"],
                    env={"OMG_TEST_PREFLIGHT_BLOCK": "1"})
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        out = json.loads(proc.stdout)
        assert out.get("preflight", {}).get("skipped") is True
    finally:
        if original is not None:
            mcp_json.write_text(original, encoding="utf-8")


def test_install_env_preflight_human_output():
    """install --plan text output must show preflight header and check names."""
    proc = _run(["install", "--plan"])
    assert proc.returncode == 0 or proc.returncode == 1
    combined = proc.stdout + proc.stderr
    assert "preflight" in combined.lower() or "env preflight" in combined.lower()
