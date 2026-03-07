"""Control-plane service endpoint tests."""
from __future__ import annotations

import json
from pathlib import Path

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
