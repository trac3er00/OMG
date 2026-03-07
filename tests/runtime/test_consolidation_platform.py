from __future__ import annotations

import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from runtime.api_twin import ingest_contract, record_fixture, serve_fixture, verify_fixture
from runtime.delta_classifier import classify_project_changes
from runtime.eval_gate import evaluate_trace
from runtime.incident_replay import build_incident_pack
from runtime.data_lineage import build_lineage_manifest, validate_lineage_manifest
from runtime.contract_compiler import _check_high_risk_security_waivers
from runtime.preflight import run_preflight
from runtime.remote_supervisor import issue_local_supervisor_session, verify_local_supervisor_token
from runtime.security_check import run_security_check, security_check
from runtime.tracebank import record_trace


ROOT = Path(__file__).resolve().parents[2]


def test_packaged_wheel_includes_control_plane_registry_plugins_and_generated_artifacts(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert any(name.endswith("control_plane/service.py") for name in names)
    assert any(name.endswith("registry/verify_artifact.py") for name in names)
    assert any("plugins/dephealth/" in name for name in names)
    assert any(name.endswith(".agents/skills/omg/security-check/SKILL.md") for name in names)
    assert any(name.endswith("OMG_COMPAT_CONTRACT.md") for name in names)


def test_security_check_emits_provenance_trust_scores_and_evidence_file(tmp_path: Path) -> None:
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    result = run_security_check(project_dir=str(tmp_path), scope=".")

    assert result["schema"] == "SecurityCheckResult"
    assert result["summary"]["finding_count"] >= 1
    assert result["summary"]["scan_status"] == "completed"
    assert result["provenance"]
    assert "overall" in result["trust_scores"]
    assert result["security_scans"]
    assert result["unresolved_risks"]
    assert all("exploitability" in finding and "reachability" in finding for finding in result["findings"])
    assert result["evidence"]["sarif_path"].endswith(".sarif")
    assert result["evidence"]["sbom_path"].endswith(".cdx.json")
    assert result["evidence"]["license_path"].endswith(".json")
    evidence_path = Path(tmp_path, result["evidence"]["path"])
    sarif_path = Path(tmp_path, result["evidence"]["sarif_path"])
    sbom_path = Path(tmp_path, result["evidence"]["sbom_path"])
    license_path = Path(tmp_path, result["evidence"]["license_path"])
    assert evidence_path.exists()
    assert sarif_path.exists()
    assert sbom_path.exists()
    assert license_path.exists()

    sarif_payload = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert sarif_payload["version"] == "2.1.0"
    assert sarif_payload["runs"]
    assert sarif_payload["runs"][0]["tool"]["driver"]["name"] == "omg-security-check"

    sbom_payload = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom_payload["bomFormat"] == "CycloneDX"
    assert sbom_payload["specVersion"] == "1.4"
    assert sbom_payload["metadata"]["tools"]

    license_payload = json.loads(license_path.read_text(encoding="utf-8"))
    assert "timestamp" in license_payload
    assert isinstance(license_payload["licenses"], list)
    assert {"name", "spdx_id", "packages"}.issubset(set(license_payload["licenses"][0]))


def test_security_check_waiver_prevents_release_blocking(tmp_path: Path) -> None:
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    initial = run_security_check(project_dir=str(tmp_path), scope=".")
    assert initial["release_blocked"] is True
    finding_id = initial["findings"][0]["finding_id"]

    waived = run_security_check(
        project_dir=str(tmp_path),
        scope=".",
        waivers=[{"finding_id": finding_id, "justification": "accepted short-term risk"}],
    )

    assert waived["release_blocked"] is False
    assert waived["status"] == "ok"
    assert any(finding.get("waived") for finding in waived["findings"])


def test_security_check_alias_accepts_waivers_and_feeds_release_blocker(tmp_path: Path) -> None:
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    baseline = security_check(project_dir=str(tmp_path), scope=".")
    finding_id = baseline["findings"][0]["finding_id"]
    assert _check_high_risk_security_waivers(
        {
            "unresolved_risks": baseline["unresolved_risks"],
            "security_scans": baseline["security_scans"],
        }
    )

    waived = security_check(
        project_dir=str(tmp_path),
        scope=".",
        waivers=[{"id": finding_id, "justification": "accepted mitigation window"}],
    )

    assert waived["release_blocked"] is False
    assert _check_high_risk_security_waivers(
        {
            "unresolved_risks": waived["unresolved_risks"],
            "security_scans": waived["security_scans"],
        }
    ) == []


def test_api_twin_supports_versioned_endpoint_cassettes_latency_and_saved_costs(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")

    ingest = ingest_contract(str(tmp_path), name="demo", source_path=str(contract))
    assert ingest["fidelity"] == "schema-only"

    record = record_fixture(
        str(tmp_path),
        name="demo",
        endpoint="GET /users",
        cassette_version="v1",
        request={"path": "/users"},
        response={"users": []},
        validated=True,
        redactions={"token": "***"},
    )
    assert record["cassette_version"] == "v1"
    assert record["endpoint"] == "GET /users"

    started = time.perf_counter()
    served = serve_fixture(
        str(tmp_path),
        name="demo",
        endpoint="GET /users",
        cassette_version="v1",
        latency_ms=25,
    )
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.02
    assert served["report"]["saved_live_calls"] == 1
    assert served["report"]["saved_cost_estimate"] >= 0

    verified = verify_fixture(
        str(tmp_path),
        name="demo",
        endpoint="GET /users",
        cassette_version="v1",
        live_response={"users": []},
    )
    assert verified["fidelity"] == "recorded-validated"


def test_preflight_uses_repo_state_tracebank_and_delta_classification(tmp_path: Path) -> None:
    (tmp_path / "auth_service.py").write_text("API_TOKEN = 'redacted'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"name": "demo", "dependencies": {"express": "^4.18.0"}}), encoding="utf-8")

    result = run_preflight(str(tmp_path), goal="cleanup")

    assert result["route"] == "security-check"
    assert "auth" in result["delta_classification"]["categories"]
    assert result["trace"]["trace_id"]
    assert result["evidence_plan"]


def test_platform_modules_emit_trace_eval_incident_lineage_and_supervisor_artifacts(tmp_path: Path) -> None:
    trace = record_trace(
        str(tmp_path),
        trace_type="ship",
        route="security-check",
        status="ok",
        plan={"goal": "stabilize auth"},
        verify={"tests": ["pytest -q"]},
    )
    assert Path(tmp_path, trace["path"]).exists()

    eval_result = evaluate_trace(
        str(tmp_path),
        trace_id=trace["trace_id"],
        suites=["security", "planning"],
        metrics={"security": 1.0, "planning": 0.9},
    )
    assert Path(tmp_path, eval_result["path"]).exists()

    classification = classify_project_changes(
        str(tmp_path),
        touched_files=["payments/api.py", "infra/deploy.tf"],
        goal="stabilize payments infrastructure",
    )
    assert {"payment", "infra"}.issubset(set(classification["categories"]))

    incident = build_incident_pack(
        str(tmp_path),
        title="Auth regression",
        failing_tests=["tests/test_auth.py::test_login"],
        logs=["Traceback: boom"],
        diff_summary={"files": ["auth_service.py"]},
        trace_id=trace["trace_id"],
    )
    assert Path(tmp_path, incident["path"]).exists()

    lineage = build_lineage_manifest(
        str(tmp_path),
        artifact_type="trace",
        sources=[{"kind": "repo", "path": "auth_service.py", "license": "MIT"}],
        privacy="internal",
        license="MIT",
        derivation={"trace_id": trace["trace_id"]},
        trace_id=trace["trace_id"],
    )
    assert validate_lineage_manifest(lineage)["status"] == "ok"
    assert Path(tmp_path, lineage["path"]).exists()

    session = issue_local_supervisor_session(str(tmp_path), worker_id="worker-1", shared_secret="secret")
    assert session["local_only"] is True
    assert verify_local_supervisor_token(session["token"], shared_secret="secret")["status"] == "ok"
