from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
import runtime.tracebank as tracebank
from runtime.contract_compiler import build_release_readiness, compile_contract_outputs
from runtime.data_lineage import build_lineage_manifest
from runtime.eval_gate import evaluate_trace
from runtime.forge_run_id import derive_run_seed
from runtime.omg_browser_cli import run_browser_cli


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_assemble_and_validate_proof_chain_with_linked_artifacts(tmp_path: Path) -> None:
    trace = tracebank.record_trace(
        str(tmp_path),
        trace_type="ship",
        route="security-check",
        status="ok",
        plan={"goal": "close proof chain"},
    )
    lineage = build_lineage_manifest(
        str(tmp_path),
        artifact_type="evidence-pack",
        sources=[{"kind": "repo", "path": "runtime/proof_chain.py", "license": "MIT"}],
        privacy="internal",
        license="MIT",
        derivation={"trace_id": trace["trace_id"]},
        trace_id=trace["trace_id"],
    )
    _ = evaluate_trace(
        str(tmp_path),
        trace_id=trace["trace_id"],
        suites=["security", "proof"],
        metrics={"security": 1.0, "proof": 1.0},
        lineage=lineage,
    )

    security_path = tmp_path / ".omg" / "evidence" / "security-check-proof.json"
    security_path.parent.mkdir(parents=True, exist_ok=True)
    _ = security_path.write_text(json.dumps({"schema": "SecurityCheckEvidence"}), encoding="utf-8")

    evidence_rel_path = ".omg/evidence/run-proof-chain.json"
    evidence_path = tmp_path / evidence_rel_path
    evidence = {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": "run-proof-chain",
        "timestamp": "2026-03-07T00:00:00+00:00",
        "executor": {"user": "tester", "pid": 1234},
        "environment": {"hostname": "localhost", "platform": "darwin"},
        "trace_id": trace["trace_id"],
        "trace_ids": [trace["trace_id"]],
        "lineage": lineage,
        "seed": derive_run_seed("run-proof-chain"),
        "temperature_lock": {
            "critical_model_paths": 0.0,
            "critical_tool_paths": 0.0,
        },
        "determinism_version": "forge-determinism-v1",
        "determinism_scope": "same-hardware",
        "security_scans": [{"tool": "security-check", "path": security_path.relative_to(tmp_path).as_posix()}],
        "provenance": [{"source": "security-check"}],
        "artifacts": [
            {
                "kind": "evidence",
                "path": evidence_rel_path,
                "sha256": "abc123",
                "parser": "json",
                "summary": "evidence pack",
                "trace_id": trace["trace_id"],
            }
        ],
        "claims": [
            {
                "claim_type": "release_ready",
                "artifacts": [
                    "junit.xml",
                    "coverage.xml",
                    ".omg/evidence/security-check-proof.sarif",
                    ".omg/evidence/browser-trace.zip",
                ],
                "trace_ids": [trace["trace_id"]],
            }
        ],
        "tests": [{"name": "worker_implementation", "passed": True}],
    }
    _ = evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    proof_chain = importlib.import_module("runtime.proof_chain")
    chain = proof_chain.assemble_proof_chain(str(tmp_path))
    validation = proof_chain.validate_proof_chain(chain)

    assert chain["trace_id"] == trace["trace_id"]
    assert chain["schema_version"] == 2
    assert chain["evidence_path"] == evidence_rel_path
    assert chain["lineage"]["lineage_id"] == lineage["lineage_id"]
    assert chain["seed"] == derive_run_seed("run-proof-chain")
    assert chain["determinism_version"] == "forge-determinism-v1"
    assert isinstance(chain["artifacts"], list)
    assert all("kind" in artifact for artifact in chain["artifacts"])
    assert validation["status"] == "ok"
    assert chain["status"] == "ok"


def test_validate_proof_chain_blocks_promotion_without_determinism_metadata() -> None:
    proof_chain = importlib.import_module("runtime.proof_chain")
    validation = proof_chain.validate_proof_chain(
        {
            "trace_id": "trace-1",
            "eval_id": "eval-1",
            "lineage": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
            "lineage_trace_id": "trace-1",
            "evidence_path": ".omg/evidence/run-proof-chain.json",
            "timestamp": "2026-03-10T00:00:00+00:00",
            "executor": {"user": "tester", "pid": 1234},
            "environment": {"hostname": "localhost", "platform": "darwin"},
            "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check-proof.json"}],
            "claims": [{"claim_type": "release_ready"}],
        }
    )

    assert validation["status"] == "error"
    assert "proof_chain_missing_deterministic_seed" in validation["blockers"]
    assert "proof_chain_missing_temperature_lock" in validation["blockers"]
    assert "proof_chain_missing_determinism_version" in validation["blockers"]


def test_assemble_proof_chain_normalizes_v1_payload_fixture(tmp_path: Path) -> None:
    evidence_payload = _load_fixture("evidence_v1_sample.json")
    evidence_rel_path = ".omg/evidence/evidence-v1.json"
    evidence_path = tmp_path / evidence_rel_path
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_path.write_text(json.dumps(evidence_payload, indent=2), encoding="utf-8")

    proof_chain = importlib.import_module("runtime.proof_chain")
    chain = proof_chain.assemble_proof_chain(str(tmp_path), evidence_path=evidence_rel_path)

    assert chain["schema"] == "ProofChain"
    assert chain["schema_version"] == 2
    assert chain["evidence_path"] == evidence_rel_path
    assert chain["status"] in {"ok", "error"}


def test_build_proof_gate_input_includes_claims_and_linked_evidence(tmp_path: Path) -> None:
    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)

    _ = (evidence_root / "security-check-proof.json").write_text(
        json.dumps(
            {
                "schema": "SecurityCheckResult",
                "evidence": {"sarif_path": ".omg/evidence/security-check-proof.sarif"},
            }
        ),
        encoding="utf-8",
    )
    _ = (evidence_root / "browser-evidence.json").write_text(
        json.dumps(
            {
                "schema": "BrowserEvidence",
                "artifacts": {"trace": ".omg/evidence/browser-trace.zip"},
                "metadata": {"trace_id": "trace-2"},
            }
        ),
        encoding="utf-8",
    )

    _ = (tmp_path / ".omg" / "evals" / "latest.json").parent.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".omg" / "evals" / "latest.json").write_text(
        json.dumps({"schema": "EvalGateResult", "status": "ok", "trace_id": "trace-2", "lineage": {"trace_id": "trace-2"}}),
        encoding="utf-8",
    )

    _ = (tmp_path / ".omg" / "tracebank" / "events.jsonl").parent.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".omg" / "tracebank" / "events.jsonl").write_text(
        json.dumps({"trace_id": "trace-2", "path": ".omg/tracebank/events.jsonl"}) + "\n",
        encoding="utf-8",
    )

    _ = (evidence_root / "run-proof-chain.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-proof-chain",
                "timestamp": "2026-03-07T00:00:00+00:00",
                "executor": {"user": "tester", "pid": 1234},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "trace_ids": ["trace-2"],
                "lineage": {"trace_id": "trace-2", "lineage_id": "lineage-2"},
                "seed": derive_run_seed("run-proof-chain"),
                "temperature_lock": {
                    "critical_model_paths": 0.0,
                    "critical_tool_paths": 0.0,
                },
                "determinism_version": "forge-determinism-v1",
                "determinism_scope": "same-hardware",
                "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check-proof.json"}],
                "claims": [
                    {
                        "claim_type": "release_ready",
                        "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "trace.zip"],
                        "trace_ids": ["trace-2"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    proof_chain = importlib.import_module("runtime.proof_chain")
    gate_input = proof_chain.build_proof_gate_input(str(tmp_path))

    assert gate_input["proof_chain"]["status"] == "ok"
    assert len(gate_input["claims"]) == 1
    assert gate_input["security_evidence"]["schema"] == "SecurityCheckResult"
    assert gate_input["browser_evidence"]["schema"] == "BrowserEvidence"


def test_build_proof_gate_input_prefers_playwright_adapter_evidence_when_available(tmp_path: Path) -> None:
    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)

    _ = (evidence_root / "playwright-adapter-run-42.json").write_text(
        json.dumps(
            {
                "schema": "PlaywrightAdapterEvidence",
                "summary": {"tests": 3, "failures": 0},
            }
        ),
        encoding="utf-8",
    )

    _ = (evidence_root / "browser-evidence.json").write_text(
        json.dumps(
            {
                "schema": "BrowserEvidence",
                "summary": {"tests": 1},
            }
        ),
        encoding="utf-8",
    )

    _ = (evidence_root / "run-proof-chain.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "schema_version": 2,
                "run_id": "run-proof-chain",
                "timestamp": "2026-03-07T00:00:00+00:00",
                "executor": {"user": "tester", "pid": 1234},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "security_scans": [],
                "tests": [{"name": "worker_implementation", "passed": True}],
            }
        ),
        encoding="utf-8",
    )

    proof_chain = importlib.import_module("runtime.proof_chain")
    gate_input = proof_chain.build_proof_gate_input(str(tmp_path))

    assert gate_input["browser_evidence"]["schema"] == "PlaywrightAdapterEvidence"


def test_build_proof_gate_input_accepts_browser_cli_evidence(tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/playwright" if name == "playwright" else None

    external_dir = tmp_path / "external"
    external_dir.mkdir()
    trace_path = external_dir / "trace.zip"
    trace_path.write_bytes(b"PK\x03\x04mock_trace")
    junit_path = external_dir / "junit.xml"
    junit_path.write_text("<testsuites></testsuites>", encoding="utf-8")
    screenshot_path = external_dir / "shot.png"
    screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\nmock_png")

    def fake_runner(*, command: list[str], cwd: str, goal: str) -> dict[str, object]:
        return {
            "returncode": 0,
            "trace_path": str(trace_path),
            "junit_path": str(junit_path),
            "screenshots": [str(screenshot_path)],
            "metadata": {"trace_id": "trace-browser-cli", "goal": goal},
        }

    run_result = run_browser_cli(
        goal="capture login flow",
        project_dir=tmp_path,
        which=fake_which,
        runner=fake_runner,
        isolated=True,
    )
    assert run_result["status"] == "success"

    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    _ = (evidence_root / "run-proof-chain.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "schema_version": 2,
                "run_id": "run-proof-chain",
                "timestamp": "2026-03-08T00:00:00+00:00",
                "executor": {"user": "tester", "pid": 1234},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "trace_ids": ["trace-browser-cli"],
                "lineage": {"trace_id": "trace-browser-cli", "lineage_id": "lineage-browser-cli"},
                "seed": derive_run_seed("run-proof-chain"),
                "temperature_lock": {
                    "critical_model_paths": 0.0,
                    "critical_tool_paths": 0.0,
                },
                "determinism_version": "forge-determinism-v1",
                "determinism_scope": "same-hardware",
                "security_scans": [],
                "claims": [
                    {
                        "claim_type": "release_ready",
                        "artifacts": ["junit.xml", "coverage.xml", "scan.sarif", "browser-trace.zip"],
                        "trace_ids": ["trace-browser-cli"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    proof_chain = importlib.import_module("runtime.proof_chain")
    gate_input = proof_chain.build_proof_gate_input(str(tmp_path))

    assert gate_input["browser_evidence"]["schema"] == "BrowserEvidence"
    assert gate_input["browser_evidence"]["metadata"]["trace_id"] == "trace-browser-cli"


def test_release_readiness_names_proof_chain_blocker_when_trace_link_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    _ = (evidence_root / "run-proof-missing-trace.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-proof-missing-trace",
                "timestamp": "2026-03-07T00:00:00+00:00",
                "executor": {"user": "tester", "pid": 1234},
                "environment": {"hostname": "localhost", "platform": "darwin"},
                "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check-proof.json"}],
                "provenance": [{"source": "security-check"}],
                "lineage": {"lineage_id": "lineage-1"},
                "tests": [{"name": "worker_implementation", "passed": True}],
            }
        ),
        encoding="utf-8",
    )

    eval_root = tmp_path / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    _ = (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "eval_id": "eval-1",
                "status": "ok",
                "summary": {"regressed": False},
                "lineage": {"lineage_id": "lineage-1"},
            }
        ),
        encoding="utf-8",
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert "proof_chain_linkage: proof_chain_missing_trace_id" in readiness["blockers"]
