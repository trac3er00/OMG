"""Control-plane service endpoint tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.service import ControlPlaneService


def test_policy_evaluate_bash_deny():
    service = ControlPlaneService(project_dir=".")
    status, out = service.policy_evaluate({"tool": "Bash", "input": {"command": "rm -rf /"}})
    assert status == 200
    assert out["action"] == "deny"
    assert out["risk_level"] == "critical"


def test_trust_review_returns_structured_report():
    service = ControlPlaneService(project_dir=".")
    status, out = service.trust_review(
        {
            "file_path": "settings.json",
            "old_config": {"permissions": {"allow": ["Read"]}},
            "new_config": {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}},
        }
    )
    assert status == 200
    assert out["verdict"] == "deny"
    assert out["risk_level"] == "critical"


def test_trust_review_detects_current_permission_syntax():
    service = ControlPlaneService(project_dir=".")
    status, out = service.trust_review(
        {
            "file_path": "settings.json",
            "old_config": {"permissions": {"allow": ["Read"]}},
            "new_config": {"permissions": {"allow": ["Read", "Bash(curl *)"]}},
        }
    )
    assert status == 200
    assert out["verdict"] == "deny"
    assert out["risk_level"] == "critical"


def test_evidence_ingest_writes_file(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.evidence_ingest(
        {
            "run_id": "run-1",
            "tests": [{"name": "pytest", "exit": 0}],
            "security_scans": [],
            "diff_summary": {"files": 1},
            "reproducibility": {"cmd": "pytest -q"},
            "unresolved_risks": [],
            "provenance": [],
            "trust_scores": {},
            "api_twin": {},
            "claims": [{"claim_type": "release_ready", "trace_ids": ["trace-1"]}],
            "test_delta": {"changed": ["runtime/proof_chain.py"]},
            "browser_evidence_path": ".omg/evidence/playwright-adapter-run-1.json",
            "repro_pack_path": ".omg/evidence/repro-pack-run-1.json",
        }
    )
    assert status == 202
    assert out["status"] == "accepted"
    ev_file = tmp_path / out["evidence_path"]
    assert ev_file.exists()
    payload = json.loads(ev_file.read_text(encoding="utf-8"))
    assert payload["provenance"] == []
    assert payload["trust_scores"] == {}
    assert payload["api_twin"] == {}
    assert payload["claims"] == [{"claim_type": "release_ready", "trace_ids": ["trace-1"]}]
    assert payload["test_delta"] == {"changed": ["runtime/proof_chain.py"]}
    assert payload["browser_evidence_path"] == ".omg/evidence/playwright-adapter-run-1.json"
    assert payload["repro_pack_path"] == ".omg/evidence/repro-pack-run-1.json"


def test_evidence_ingest_rejects_invalid_run_id(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.evidence_ingest(
        {
            "run_id": "../../pwned",
            "tests": [],
            "security_scans": [],
            "diff_summary": {},
            "reproducibility": {},
            "unresolved_risks": [],
        }
    )
    assert status == 400
    assert out["error_code"] == "INVALID_EVIDENCE_INPUT"
    assert not (tmp_path / "pwned.json").exists()


def test_runtime_dispatch_unknown_runtime():
    service = ControlPlaneService(project_dir=".")
    status, out = service.runtime_dispatch({"runtime": "unknown", "idea": {"goal": "x"}})
    assert status == 400
    assert out["error_code"] == "RUNTIME_NOT_FOUND"


def test_security_check_returns_structured_findings(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({"scope": "."})
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"
    assert out["summary"]["finding_count"] >= 1
    assert any(finding["category"] == "python_ast" for finding in out["findings"])


def test_guide_assert_reports_rule_violations():
    service = ControlPlaneService(project_dir=".")
    status, out = service.guide_assert(
        {
            "candidate": "Uses TODO markers and insecure defaults.",
            "rules": {
                "goals": ["Avoid TODO markers in final output"],
                "non_goals": ["Do not mention insecure defaults"],
                "acceptance_criteria": ["Must be production-ready prose"],
            },
        }
    )
    assert status == 200
    assert out["schema"] == "GuideAssertionResult"
    assert out["verdict"] == "fail"
    assert out["violations"]


def test_registry_verify_blocks_critical():
    service = ControlPlaneService(project_dir=".")
    status, out = service.registry_verify(
        {
            "artifact": {
                "id": "bad",
                "signer": "ok",
                "checksum": "sha256:abc",
                "permissions": [],
                "static_scan": [{"severity": "critical"}],
            }
        }
    )
    assert status == 200
    assert out["action"] == "deny"


def test_lab_jobs_block_invalid_policy():
    service = ControlPlaneService(project_dir=".")
    status, out = service.lab_jobs(
        {
            "dataset": {"source": "clean-source", "license": "proprietary"},
            "base_model": {"source": "open-model", "allow_distill": True},
        }
    )
    assert status == 400
    assert out["status"] == "blocked"


def test_scoreboard_baseline_shape():
    service = ControlPlaneService(project_dir=".")
    status, out = service.scoreboard_baseline()
    assert status == 200
    assert "baseline" in out
    assert set(out["baseline"].keys()) == {
        "safe_autonomy_rate",
        "pr_throughput",
        "adoption_velocity",
    }


def test_security_check_forwards_external_inputs(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    external_inputs = [{"source": "browser", "content": "user input"}]
    status, out = service.security_check({
        "scope": ".",
        "external_inputs": external_inputs,
    })
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"
    assert out["provenance"] is not None


def test_security_check_rejects_malformed_external_inputs_not_list(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "external_inputs": "not a list",
    })
    assert status == 400
    assert out["error_code"] == "INVALID_EXTERNAL_INPUTS"
    assert "must be a list" in out["message"]


def test_security_check_rejects_malformed_external_inputs_non_dict_items(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "external_inputs": ["not a dict"],
    })
    assert status == 400
    assert out["error_code"] == "INVALID_EXTERNAL_INPUTS"
    assert "must be an object" in out["message"]


def test_security_check_accepts_none_external_inputs(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "external_inputs": None,
    })
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"


def test_security_check_accepts_waivers(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "waivers": ["shell-true"],
    })
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"


def test_security_check_accepts_none_waivers(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "waivers": None,
    })
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"


def test_security_check_rejects_malformed_waivers_not_list(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "waivers": "not a list",
    })
    assert status == 400
    assert out["error_code"] == "INVALID_WAIVERS"
    assert "must be a list" in out["message"]


def test_security_check_rejects_malformed_waivers_non_str_items(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "waivers": [42],
    })
    assert status == 400
    assert out["error_code"] == "INVALID_WAIVERS"
    assert "string or object" in out["message"]


def test_security_check_accepts_dict_waivers(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.security_check({
        "scope": ".",
        "waivers": [{"id": "shell-true", "reason": "accepted risk"}],
    })
    assert status == 200
    assert out["schema"] == "SecurityCheckResult"


def test_claim_judge_returns_results(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    claims = [
        {
            "claim_type": "test_pass",
            "subject": "auth",
            "artifacts": [".omg/evidence/run-1.json"],
            "trace_ids": ["t-1"],
        }
    ]
    status, out = service.claim_judge({"claims": claims})
    assert status == 200
    assert out["schema"] == "ClaimJudgeResults"
    assert out["verdict"] in {"pass", "fail", "insufficient"}
    assert isinstance(out["results"], list)


def test_claim_judge_rejects_missing_claims():
    service = ControlPlaneService(project_dir=".")
    status, out = service.claim_judge({})
    assert status == 400
    assert out["error_code"] == "INVALID_CLAIM_INPUT"


def test_claim_judge_rejects_non_list_claims():
    service = ControlPlaneService(project_dir=".")
    status, out = service.claim_judge({"claims": "not-a-list"})
    assert status == 400
    assert out["error_code"] == "INVALID_CLAIM_INPUT"


def test_test_intent_lock_lock_action(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.test_intent_lock({
        "action": "lock",
        "intent": {"tests": ["test_auth"]},
    })
    assert status == 200
    assert out["status"] == "locked"
    assert "lock_id" in out


def test_test_intent_lock_verify_action(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    _, lock_out = service.test_intent_lock({
        "action": "lock",
        "intent": {"tests": ["test_auth"]},
    })
    lock_id = lock_out["lock_id"]

    status, out = service.test_intent_lock({
        "action": "verify",
        "lock_id": lock_id,
        "results": {"tests": ["test_auth"]},
    })
    assert status == 200
    assert out["status"] == "ok"
    assert out["lock_id"] == lock_id


def test_test_intent_lock_rejects_unknown_action():
    service = ControlPlaneService(project_dir=".")
    status, out = service.test_intent_lock({"action": "unknown"})
    assert status == 400
    assert out["error_code"] == "INVALID_INTENT_ACTION"


def test_test_intent_lock_rejects_lock_without_intent():
    service = ControlPlaneService(project_dir=".")
    status, out = service.test_intent_lock({"action": "lock"})
    assert status == 400
    assert out["error_code"] == "INVALID_INTENT_INPUT"


def test_test_intent_lock_rejects_verify_without_lock_id():
    service = ControlPlaneService(project_dir=".")
    status, out = service.test_intent_lock({
        "action": "verify",
        "results": {"tests": ["test_auth"]},
    })
    assert status == 400
    assert out["error_code"] == "INVALID_INTENT_INPUT"


def test_test_intent_lock_rejects_verify_without_results():
    service = ControlPlaneService(project_dir=".")
    status, out = service.test_intent_lock({
        "action": "verify",
        "lock_id": "some-id",
    })
    assert status == 400
    assert out["error_code"] == "INVALID_INTENT_INPUT"


def test_mutation_gate_check_blocks_mutation_without_lock(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.mutation_gate_check({"tool": "Write", "file_path": "src/app.py"})
    assert status == 200
    assert out["status"] == "blocked"


def test_mutation_gate_check_allows_with_valid_lock(tmp_path: Path):
    lock_dir = tmp_path / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "active-lock.json").write_text("{}", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    status, out = service.mutation_gate_check({
        "tool": "Edit",
        "file_path": "src/app.py",
        "lock_id": "active-lock",
    })
    assert status == 200
    assert out["status"] == "allowed"


def test_mutation_gate_check_rejects_invalid_payload(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    with pytest.raises(ValueError, match="tool is required"):
        _ = service.mutation_gate_check({"file_path": "src/app.py"})


def test_session_health_returns_state_by_run_id(tmp_path: Path):
    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "svc-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "svc-1",
            "status": "ok",
            "contamination_risk": 0.15,
            "overthinking_score": 0.2,
            "context_health": 0.85,
            "verification_status": "ok",
            "recommended_action": "continue",
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, result = service.session_health({"run_id": "svc-1"})
    assert status == 200
    assert result["schema"] == "SessionHealth"
    assert result["run_id"] == "svc-1"


def test_session_health_returns_latest_when_no_run_id(tmp_path: Path):
    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "auto-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "auto-1",
            "status": "ok",
            "contamination_risk": 0.1,
            "overthinking_score": 0.1,
            "context_health": 0.9,
            "verification_status": "ok",
            "recommended_action": "continue",
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, result = service.session_health({})
    assert status == 200
    assert result["schema"] == "SessionHealth"
    assert result["run_id"] == "auto-1"


def test_session_health_returns_404_when_missing(tmp_path: Path):
    service = ControlPlaneService(project_dir=str(tmp_path))
    status, result = service.session_health({"run_id": "nonexistent"})
    assert status == 404
