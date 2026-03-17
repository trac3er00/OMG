from __future__ import annotations

import importlib
import json
from unittest.mock import patch

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
