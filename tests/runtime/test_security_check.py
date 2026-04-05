from __future__ import annotations
# pyright: reportMissingImports=false

import importlib
import json
from unittest.mock import patch

import pytest

from runtime.security_check import run_security_check, run_semgrep_scan


def test_run_semgrep_scan_returns_unavailable_when_binary_missing(tmp_path):
    with patch("runtime.security_check.shutil.which", return_value=None):
        result = run_semgrep_scan(str(tmp_path))

    assert result == {
        "status": "unavailable",
        "findings": [],
        "error": "semgrep not found",
    }


def test_run_semgrep_scan_normalizes_findings_when_available(tmp_path):
    semgrep_payload = {
        "results": [
            {
                "check_id": "python.lang.security.audit.subprocess-shell-true",
                "path": "src/app.py",
                "start": {"line": 12},
                "extra": {"message": "Avoid shell=True", "severity": "ERROR"},
            }
        ]
    }

    class _Proc:
        returncode = 0
        stdout = json.dumps(semgrep_payload)
        stderr = ""

    with patch("runtime.security_check.shutil.which", return_value="/usr/local/bin/semgrep"):
        with patch("runtime.security_check.subprocess.run", return_value=_Proc()):
            result = run_semgrep_scan(str(tmp_path), rules="auto")

    assert result["status"] == "ok"
    assert result["error"] == ""
    assert result["findings"] == [
        {
            "severity": "high",
            "rule": "python.lang.security.audit.subprocess-shell-true",
            "path": "src/app.py",
            "line": 12,
            "message": "Avoid shell=True",
        }
    ]


def test_run_security_check_emits_evidence_requirements(tmp_path):
    registry = importlib.import_module("runtime.evidence_requirements")
    result = run_security_check(project_dir=str(tmp_path), scope=".", include_live_enrichment=False)

    assert result["summary"]["delta_evidence_profile"] == "security-audit"
    assert result["evidence_requirements"] == registry.FULL_REQUIREMENTS
    assert result["summary"]["evidence_requirements"] == registry.FULL_REQUIREMENTS


def test_run_security_check_fail_closed_when_profile_missing(tmp_path):
    registry = importlib.import_module("runtime.evidence_requirements")
    with patch(
        "runtime.security_check.classify_project_changes",
        return_value={"categories": ["implementation"], "touched_files": []},
    ):
        result = run_security_check(project_dir=str(tmp_path), scope=".", include_live_enrichment=False)

    assert result["evidence_requirements"] == registry.FULL_REQUIREMENTS
    assert result["summary"]["evidence_requirements"] == registry.FULL_REQUIREMENTS


def test_run_semgrep_scan_handles_malformed_json_without_crash(tmp_path):
    class _Proc:
        returncode = 0
        stdout = "not-json"
        stderr = ""

    with patch("runtime.security_check.shutil.which", return_value="/usr/local/bin/semgrep"):
        with patch("runtime.security_check.subprocess.run", return_value=_Proc()):
            result = run_semgrep_scan(str(tmp_path))

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert "semgrep" in result["error"]


def test_run_security_check_callable_for_forge_integration(tmp_path):
    """Ensure run_security_check works as standalone callable for Forge reuse."""
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    assert result["schema"] == "SecurityCheckResult"
    assert "security_scans" in result
    assert isinstance(result["security_scans"], list)
    assert "evidence" in result
    assert "sarif_path" in result["evidence"]
    assert "sbom_path" in result["evidence"]
    assert "unresolved_risks" in result
    assert isinstance(result["findings"], list)


def test_excluded_directories_stay_out_of_scan(tmp_path):
    """Verify that excluded directories are not scanned."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "danger.py").write_text("import subprocess\nsubprocess.run('cmd', shell=True)")
    
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "danger.py").write_text("import subprocess\nsubprocess.run('cmd', shell=True)")
    
    (tmp_path / ".sisyphus").mkdir()
    (tmp_path / ".sisyphus" / "evidence.txt").write_text("subprocess.run('cmd', shell=True)")
    
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("exec('cmd')")
    
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "extracted").mkdir()
    (tmp_path / "dist" / "extracted" / "danger.py").write_text("import subprocess\nsubprocess.run('cmd', shell=True)")
    
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    
    finding_paths = [f.get("path", "") for f in result["findings"]]
    for path in finding_paths:
        assert "tests" not in path.split("/"), f"tests/ should be excluded but found: {path}"
        assert ".sisyphus" not in path.split("/"), f".sisyphus/ should be excluded but found: {path}"
        assert "node_modules" not in path.split("/"), f"node_modules/ should be excluded but found: {path}"
        assert "dist" not in path.split("/"), f"dist/ should be excluded but found: {path}"


def test_included_source_paths_still_fail_closed(tmp_path):
    """Verify that included source paths are still scanned and fail closed."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "danger.py").write_text("import subprocess\nsubprocess.run('cmd', shell=True)")
    
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    
    assert result["status"] == "error", "Should fail closed when dangerous code is found"
    assert result["release_blocked"] == True, "Release should be blocked"
    
    b602_findings = [f for f in result["findings"] if f.get("id") == "B602"]
    assert len(b602_findings) > 0, "Should find B602 subprocess-shell-true violation"
    assert any("src" in f.get("evidence", {}).get("path", "").split("/") for f in b602_findings), "Should find violation in src/"


def test_docs_pem_placeholder_does_not_trigger_sec002(tmp_path):
    from runtime.security_check import run_security_check
    docs_file = tmp_path / "github-app.md"
    docs_file.write_text("The key must be in `<RSA PRIVATE KEY PEM HEADER>` format.\n")
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    sec002_findings = [f for f in result.get("findings", []) if f.get("id") == "SEC002" and not f.get("waived", False)]
    assert sec002_findings == []


def test_real_pem_header_still_triggers_sec002(tmp_path):
    from runtime.security_check import run_security_check
    pem_file = tmp_path / "secret.md"
    pem_file.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n")
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    sec002 = [f for f in result.get("findings", []) if f.get("id") == "SEC002" and not f.get("waived", False)]
    assert len(sec002) >= 1 and sec002[0].get("severity") == "critical"


def test_sanctioned_callsites_are_auto_waived(tmp_path):
    from runtime.security_check import run_security_check
    (tmp_path / "tools").mkdir()
    (tmp_path / "omg_natives").mkdir()
    (tmp_path / "tools" / "python_repl.py").write_text("eval('1+1')\nexec('x=1')\n")
    (tmp_path / "tools" / "python_sandbox.py").write_text("eval('1+1')\nexec('x=1')\n")
    (tmp_path / "omg_natives" / "shell.py").write_text("import subprocess\nsubprocess.run('echo hi', shell=True)\n")
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    sanctioned = [f for f in result.get("findings", []) if f.get("waived") and f.get("waiver_justification")]
    assert len(sanctioned) >= 5


def test_release_artifact_audit_b603_findings_require_manual_review(tmp_path):
    from runtime.security_check import _finalize_findings

    audit_file = tmp_path / "runtime" / "release_artifact_audit.py"
    audit_file.parent.mkdir()
    audit_file.write_text("import subprocess\nsubprocess.run(['echo', 'hi'])\n", encoding="utf-8")

    findings = [
        {
            "id": "B603",
            "source": "bandit",
            "category": "python_ast",
            "severity": "low",
            "message": "subprocess call - check for execution of untrusted input.",
            "recommendation": "Review subprocess usage and keep it manually approved.",
            "evidence": {
                "path": str(audit_file),
                "line": 2,
                "snippet": "subprocess.run(['echo', 'hi'])",
            },
        }
    ]

    finalized = _finalize_findings(findings, {}, project_dir=str(tmp_path))

    assert finalized[0]["waived"] is False
    assert "waiver_justification" not in finalized[0]


def test_non_sanctioned_callsites_remain_blocked(tmp_path):
    from runtime.security_check import run_security_check
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "danger.py").write_text("eval('1+1')\nimport subprocess\nsubprocess.run('echo hi', shell=True)\n")
    result = run_security_check(project_dir=str(tmp_path), scope=".")
    unwaived = [f for f in result.get("findings", []) if not f.get("waived") and f.get("id") in {"B307", "B602"}]
    assert len(unwaived) >= 1 and result.get("release_blocked") is True


def test_resolve_scope_rejects_traversal_outside_project(tmp_path):
    from runtime.security_check import _resolve_scope

    with pytest.raises(ValueError):
        _resolve_scope(str(tmp_path), "../outside")


def test_normalize_waivers_handles_mixed_formats():
    from runtime.security_check import _normalize_waivers

    waivers = _normalize_waivers([
        "B602-fixed-id",
        {"finding_id": "B307-custom", "justification": "approved legacy call"},
        {"id": "B102", "reason": "controlled runtime"},
        {"id": "", "reason": "ignored"},
    ])

    assert waivers["B602-fixed-id"] == "waived"
    assert waivers["B307-custom"] == "approved legacy call"
    assert waivers["B102"] == "controlled runtime"


def test_finalize_findings_applies_sanctioned_callsite_auto_waiver(tmp_path):
    from runtime.security_check import _finalize_findings

    callsite = tmp_path / "tools" / "python_repl.py"
    callsite.parent.mkdir(parents=True)
    callsite.write_text("eval('1+1')\n", encoding="utf-8")

    finalized = _finalize_findings(
        [
            {
                "id": "B307",
                "source": "bandit-lite",
                "category": "python_ast",
                "severity": "high",
                "message": "eval() detected",
                "recommendation": "avoid eval",
                "evidence": {"path": str(callsite), "line": 1, "snippet": "eval('1+1')"},
            }
        ],
        {},
        project_dir=str(tmp_path),
    )

    assert finalized[0]["waived"] is True
    assert "Intentional eval() in REPL backend" in finalized[0]["waiver_justification"]


def test_build_sarif_payload_marks_waived_findings_with_suppression():
    from runtime.security_check import _build_sarif_payload

    payload = _build_sarif_payload(
        [
            {
                "id": "SEC002",
                "category": "secret",
                "severity": "critical",
                "message": "Private key material detected",
                "recommendation": "remove",
                "finding_id": "SEC002-abc123",
                "waived": True,
                "waiver_justification": "approved fixture",
                "exploitability": "high",
                "reachability": "reachable",
                "evidence": {"path": "secrets/key.pem", "line": 4, "snippet": "-----BEGIN RSA PRIVATE KEY-----"},
            }
        ]
    )

    result = payload["runs"][0]["results"][0]
    assert result["level"] == "error"
    assert result["suppressions"][0]["justification"] == "approved fixture"
