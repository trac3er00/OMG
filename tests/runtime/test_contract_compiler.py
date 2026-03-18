from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
from unittest.mock import patch

import pytest
import yaml
from runtime.adoption import CANONICAL_VERSION
from runtime.canonical_surface import get_canonical_hosts
from runtime.evidence_requirements import requirements_for_profile
from runtime import contract_compiler as contract_compiler_module
from runtime.release_surfaces import get_authored_paths
from runtime.contract_compiler import (
    DEFAULT_REQUIRED_BUNDLES,
    REQUIRED_CLAUDE_HOOK_EVENTS,
    REQUIRED_CLAUDE_SUBAGENT_NAMES,
    REQUIRED_CODEX_AGENTS_SECTIONS,
    REQUIRED_CODEX_OUTPUTS,
    _get_required_advanced_plugin_artifacts,
    _check_release_surface_drift,
    _check_policy_pack_signatures,
    check_package_parity,
    build_release_readiness,
    compile_contract_outputs,
    validate_contract_registry,
    _check_plugin_command_paths,
    _validate_compiled_claude_output,
    _validate_compiled_codex_output,
)

# The four truth/council bundles that must always be present in canonical surfaces.
TRUTH_COUNCIL_BUNDLES = ("plan-council", "claim-judge", "test-intent-lock", "proof-gate")
CANONICAL_HOSTS = tuple(get_canonical_hosts())


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stub_registry_validation_for_non_registry_tests(monkeypatch, request) -> None:
    registry_tests = {
        "test_validate_contract_registry_reports_expected_bundles",
        "test_validate_contract_registry_accepts_valid_policy_model",
        "test_validate_contract_registry_rejects_malformed_host_rules",
        "test_validate_contract_registry_accepts_gemini_kimi_host_rules",
        "test_validate_contract_registry_rejects_incomplete_gemini_host_rules",
    }
    if request.node.name in registry_tests:
        return
    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root=None: {
            "schema": "OmgContractValidationResult",
            "status": "ok",
            "errors": [],
            "contract": {},
            "bundles": [],
        },
    )


def _patch_fast_release_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_packaged_install_smoke",
        lambda _root: {"status": "ok", "blockers": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_mcp_fabric",
        lambda: {"ready": True, "prompt_count": 1, "resource_count": 1},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_version_identity_drift",
        lambda _root: {
            "status": "ok",
            "canonical_version": CANONICAL_VERSION,
            "blockers": [],
            "drift_details": {},
        },
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "check_package_parity",
        lambda _root: {
            "status": "ok",
            "required_surfaces": ["hash-edit", "ast-pack", "terminal-lane"],
            "machine_blockers": [],
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_release_surface_drift",
        lambda _root, _output: {
            "status": "ok",
            "blockers": [],
            "checks": {},
        },
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_policy_pack_signatures",
        lambda _root: {
            "status": "ok",
            "enforcing": False,
            "blockers": [],
        },
    )


def _patch_proof_chain_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_proof_chain",
        lambda _output_root: {
            "status": "ok",
            "proof_chain": {"status": "ok", "blockers": []},
            "proof_gate": {"verdict": "pass", "blockers": []},
            "blockers": [],
        },
    )


def _patch_claim_judge_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_compiler_module,
        "evaluate_release_compliance",
        lambda **_kw: {"status": "allowed", "authority": "release", "reason": "fixture"},
    )


def _write_claim_judge_evidence(output_root: Path, *, run_id: str = "run-1") -> None:
    evidence_root = output_root / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / f"claim-judge-{run_id}.json").write_text(
        json.dumps({"schema": "ClaimJudgeOutcome", "run_id": run_id, "status": "allowed"}),
        encoding="utf-8",
    )


def _write_doctor_success(output_root: Path) -> None:
    doctor_path = output_root / ".omg" / "evidence" / "doctor.json"
    doctor_path.parent.mkdir(parents=True, exist_ok=True)
    doctor_path.write_text(
        json.dumps(
            {
                "schema": "DoctorResult",
                "status": "pass",
                "checks": [{"name": "python_version", "status": "ok", "required": True}],
            }
        ),
        encoding="utf-8",
    )


def _write_eval_ok(output_root: Path) -> None:
    eval_root = output_root / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "status": "ok",
                "summary": {"regressed": False},
            }
        ),
        encoding="utf-8",
    )


def _write_evidence(
    output_root: Path,
    *,
    include_lineage: bool = True,
    include_attribution: bool = True,
    unresolved_risks: list[dict[str, object] | str] | None = None,
    include_claims: bool = True,
) -> None:
    payload: dict[str, object] = {
        "schema": "EvidencePack",
        "run_id": "run-1",
        "context_checksum": "ctx-run-1",
        "profile_version": "profile-v1",
        "intent_gate_version": "1.0.0",
        "tests": [{"name": "worker_implementation", "passed": True}],
        "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check.json"}],
        "diff_summary": {"files": 1},
        "reproducibility": {"cmd": "pytest -q"},
        "unresolved_risks": unresolved_risks or [],
        "provenance": [{"source": "security-check"}],
        "trust_scores": {"overall": 1.0},
        "api_twin": {},
        "trace_ids": ["trace-1"],
        "lineage": {"lineage_id": "lineage-1"} if include_lineage else {},
        "intent_gate_state": {"path": ".omg/state/intent_gate/run-1.json", "run_id": "run-1"},
        "profile_digest": {"path": ".omg/state/profile.yaml", "profile_version": "profile-v1"},
        "session_health_state": {"path": ".omg/state/session_health/run-1.json", "run_id": "run-1"},
        "council_verdicts": {"path": ".omg/state/council_verdicts/run-1.json", "run_id": "run-1"},
        "forge_starter_proof": {"path": ".omg/evidence/forge-specialists-run-1.json", "run_id": "run-1"},
        "exec_kernel_state": {"path": ".omg/state/exec-kernel/run-1.json", "run_id": "run-1"},
        "worker_watchdog_replay": {"path": ".omg/evidence/subagents/run-1-replay.json", "run_id": "run-1"},
        "merge_writer_provenance": {"path": ".omg/evidence/merge-writer-run-1.json", "run_id": "run-1"},
        "write_lease_provenance": {"path": ".omg/evidence/write-lease-run-1.json", "run_id": "run-1"},
        "tool_fabric_ledger": {"path": ".omg/state/ledger/tool-ledger.jsonl", "run_id": "run-1"},
        "budget_envelope_state": {"path": ".omg/state/budget-envelopes/run-1.json", "run_id": "run-1"},
        "issue_report": {"path": ".omg/evidence/issues/run-1.json", "run_id": "run-1"},
        "host_parity_report": {"path": ".omg/evidence/host-parity-run-1.json", "run_id": "run-1"},
        "music_omr_testbed_evidence": {"path": ".omg/evidence/music-omr-run-1.json", "run_id": "run-1"},
    }
    if include_claims:
        payload["claims"] = [
            {
                "claim_type": "release_ready",
                "artifacts": [
                    "reports/junit.xml",
                    "reports/coverage.xml",
                    ".omg/evidence/security-check.sarif",
                    ".omg/evidence/playwright-trace.zip",
                ],
                "trace_ids": ["trace-1"],
            }
        ]
    if include_attribution:
        payload.update(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "executor": {"user": "tester", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "darwin"},
            }
        )

    evidence_root = output_root / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "run-1.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_execution_primitives(output_root: Path, *, run_id: str = "run-1") -> None:
    context_checksum = f"ctx-{run_id}"
    profile_version = "profile-v1"
    intent_gate_version = "1.0.0"
    state_root = output_root / ".omg" / "state"
    (state_root / "release_run_coordinator").mkdir(parents=True, exist_ok=True)
    (state_root / "release_run_coordinator" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "ReleaseRunCoordinatorState",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "ok",
                "phase": "finalize",
                "resolution_source": "test",
                "resolution_reason": "fixture",
                "compliance_authority": "release",
                "compliance_reason": "compliance checks passed",
                "updated_at": "2026-01-01T00:00:00Z",
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
            }
        ),
        encoding="utf-8",
    )

    (state_root / "test-intent-lock").mkdir(parents=True, exist_ok=True)
    (state_root / "test-intent-lock" / "lock-1.json").write_text(
        json.dumps(
            {
                "schema": "TestIntentLock",
                "schema_version": "1.0.0",
                "lock_id": "lock-1",
                "run_id": run_id,
                "status": "ok",
                "intent": {"run_id": run_id},
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
            }
        ),
        encoding="utf-8",
    )

    (state_root / "rollback_manifest").mkdir(parents=True, exist_ok=True)
    (state_root / "rollback_manifest" / f"{run_id}-step-1.json").write_text(
        json.dumps(
            {
                "schema": "RollbackManifest",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "ok",
                "step_id": "step-1",
                "local_restores": [],
                "compensating_actions": [],
                "side_effects": [],
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    (state_root / "session_health").mkdir(parents=True, exist_ok=True)
    (state_root / "session_health" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "SessionHealth",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "ok",
                "contamination_risk": 0.1,
                "overthinking_score": 0.1,
                "context_health": 0.9,
                "verification_status": "ok",
                "recommended_action": "continue",
                "updated_at": "2026-01-01T00:00:00Z",
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
            }
        ),
        encoding="utf-8",
    )

    (state_root / "intent_gate").mkdir(parents=True, exist_ok=True)
    (state_root / "intent_gate" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "IntentGateDecision",
                "schema_version": intent_gate_version,
                "run_id": run_id,
                "intent_gate_version": intent_gate_version,
                "requires_clarification": False,
                "intent_class": "release_readiness",
                "clarification_prompt": "",
                "confidence": 0.98,
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    (state_root / "profile.yaml").write_text(
        "\n".join(
            [
                "profile_version: profile-v1",
                "preferences:",
                "  architecture_requests:",
                "    - release_readiness",
                "user_vector:",
                "  summary: compiler fixture profile",
                "profile_provenance:",
                "  checksum: profile-v1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (state_root / "council_verdicts").mkdir(parents=True, exist_ok=True)
    (state_root / "council_verdicts" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "CouncilVerdicts",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "ok",
                "verification_status": "ok",
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
                "verdicts": {"skeptic": {"verdict": "pass"}},
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    evidence_root = output_root / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / f"forge-specialists-{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "ForgeSpecialistDispatchEvidence",
                "schema_version": "1.0.0",
                "run_id": run_id,
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

    # --- 8 new execution primitives (Phase 1 Pro Release Kernel) ---
    exec_kernel_dir = state_root / "exec-kernel"
    exec_kernel_dir.mkdir(parents=True, exist_ok=True)
    (exec_kernel_dir / f"{run_id}.json").write_text(
        json.dumps({"schema": "ExecKernelRunState", "run_id": run_id, "status": "queued", "kernel_enabled": True}),
        encoding="utf-8",
    )

    subagents_dir = evidence_root / "subagents"
    subagents_dir.mkdir(parents=True, exist_ok=True)
    (subagents_dir / f"{run_id}-replay.json").write_text(
        json.dumps({"schema": "WorkerReplayEvidence", "run_id": run_id, "reason": "completed"}),
        encoding="utf-8",
    )

    (evidence_root / f"merge-writer-{run_id}.json").write_text(
        json.dumps({
            "schema": "MergeWriterProvenance",
            "run_id": run_id,
            "acquired_at": "2026-01-01T00:00:00Z",
            "released_at": "2026-01-01T00:00:01Z",
        }),
        encoding="utf-8",
    )

    (evidence_root / f"write-lease-{run_id}.json").write_text(
        json.dumps({
            "schema": "WriteLeaseProvenance",
            "run_id": run_id,
            "created_at": "2026-01-01T00:00:00Z",
            "duration_s": 3600.0,
            "evidence_path": f".omg/evidence/merge-writer-{run_id}.json",
        }),
        encoding="utf-8",
    )

    ledger_dir = state_root / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "tool-ledger.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "tool": "ls", "run_id": run_id}) + "\n",
        encoding="utf-8",
    )

    budget_dir = state_root / "budget-envelopes"
    budget_dir.mkdir(parents=True, exist_ok=True)
    (budget_dir / f"{run_id}.json").write_text(
        json.dumps({"schema": "BudgetEnvelopeState", "run_id": run_id, "usage": {"cpu_seconds_used": 0.1}}),
        encoding="utf-8",
    )

    issues_dir = evidence_root / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    (issues_dir / f"{run_id}.json").write_text(
        json.dumps({"schema": "IssueReport", "run_id": run_id, "issues": []}),
        encoding="utf-8",
    )

    (evidence_root / f"host-parity-{run_id}.json").write_text(
        json.dumps({
            "schema": "HostParityReport",
            "run_id": run_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "canonical_hosts": list(CANONICAL_HOSTS),
            "parity_results": {
                "passed": True,
                "drift_detected": False,
                "drift_details": [],
                "host_results": {
                    "claude": {
                        "present": True,
                        "passed": True,
                        "reason": "baseline",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": "settings.json",
                        },
                    },
                    "codex": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".agents/skills/omg/AGENTS.fragment.md",
                        },
                    },
                    "gemini": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".gemini/settings.json",
                        },
                    },
                    "kimi": {
                        "present": True,
                        "passed": True,
                        "reason": "structured-equivalent",
                        "normalized": {
                            "source_class": "compiled_or_replayed",
                            "source_kind": "compiled_artifact",
                            "source_path": ".kimi/mcp.json",
                        },
                    },
                },
            },
            "overall_status": "ok",
        }),
        encoding="utf-8",
    )

    (evidence_root / f"music-omr-{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "MusicOMREvidence",
                "schema_version": "2.1.0",
                "run_id": run_id,
                "trace_metadata": {"run_id_linkage": run_id},
                "freshness": {"generated_at": datetime.now(timezone.utc).isoformat(), "max_age_seconds": 86400},
                "results": {},
            }
        ),
        encoding="utf-8",
    )


def test_release_readiness_accepts_schema_v2_evidence_fixture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    fixture_payload = json.loads(
        (ROOT / "tests" / "runtime" / "fixtures" / "evidence_v2_sample.json").read_text(encoding="utf-8")
    )
    fixture_run_id = str(fixture_payload.get("run_id", "run-v2"))
    fixture_payload["provenance"] = [{"source": "security-check"}]
    fixture_payload["tests"] = [{"name": "worker_implementation", "passed": True}]
    fixture_payload["context_checksum"] = "ctx-run-v2"
    fixture_payload["profile_version"] = "profile-v1"
    fixture_payload["intent_gate_version"] = "1.0.0"
    fixture_payload["claims"] = [
        {
            "claim_type": "release_ready",
            "artifacts": [
                "reports/junit.xml",
                "reports/coverage.xml",
                ".omg/evidence/security-check.sarif",
                ".omg/evidence/playwright-trace.zip",
            ],
            "trace_ids": ["trace-1"],
        }
    ]

    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "run-v2.json").write_text(json.dumps(fixture_payload), encoding="utf-8")
    _write_execution_primitives(tmp_path, run_id=fixture_run_id)
    _write_claim_judge_evidence(tmp_path, run_id=fixture_run_id)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    normalize_calls = {"count": 0}
    normalize_impl = contract_compiler_module._normalize_evidence_pack

    def tracking_normalize(payload: dict[str, object]) -> dict[str, object]:
        normalize_calls["count"] += 1
        return normalize_impl(payload)

    monkeypatch.setattr(contract_compiler_module, "_normalize_evidence_pack", tracking_normalize)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "ok", readiness["blockers"]
    assert normalize_calls["count"] >= 1
    primitives = readiness["checks"]["execution_primitives"]
    assert "intent_gate_state" in primitives["required"]
    assert "profile_digest" in primitives["required"]
    assert primitives["evidence_paths"]["intent_gate_state"] == f".omg/state/intent_gate/{fixture_run_id}.json"
    assert primitives["evidence_paths"]["profile_digest"] == ".omg/state/profile.yaml"


def test_validate_contract_registry_reports_expected_bundles() -> None:
    result = validate_contract_registry(ROOT)

    assert result["schema"] == "OmgContractValidationResult"
    assert result["contract"]["version"] == CANONICAL_VERSION
    bundle_ids = {bundle["id"] for bundle in result["bundles"]}
    assert {
        "control-plane",
        "plan-council",
        "hook-governor",
        "mcp-fabric",
        "lsp-pack",
        "secure-worktree-pipeline",
        "security-check",
        "api-twin",
        "preflight",
        "robotics",
        "vision",
        "algorithms",
        "health",
        "tracebank",
        "eval-gate",
        "delta-classifier",
        "incident-replay",
        "data-lineage",
        "remote-supervisor",
        "proof-gate",
    }.issubset(bundle_ids)


def test_validate_contract_registry_accepts_valid_policy_model() -> None:
    result = validate_contract_registry(ROOT)

    assert not [error for error in result["errors"] if "policy_model" in error]


def test_validate_contract_registry_rejects_malformed_host_rules(tmp_path: Path) -> None:
    fixture_root = tmp_path / "repo"
    (fixture_root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", fixture_root / "OMG_COMPAT_CONTRACT.md")
    shutil.copy2(ROOT / "registry" / "omg-capability.schema.json", fixture_root / "registry" / "omg-capability.schema.json")
    shutil.copytree(ROOT / "registry" / "bundles", fixture_root / "registry" / "bundles")

    control_plane_path = fixture_root / "registry" / "bundles" / "control-plane.yaml"
    control_plane = yaml.safe_load(control_plane_path.read_text(encoding="utf-8"))
    del control_plane["policy_model"]["host_rules"]["codex"]["automations"]
    dumped = yaml.safe_dump(control_plane, sort_keys=False)
    assert isinstance(dumped, str)
    control_plane_path.write_text(dumped, encoding="utf-8")

    result = validate_contract_registry(fixture_root)

    assert result["status"] == "error"
    assert any(
        error == "control-plane: malformed host_rules entry for codex: missing 'automations'"
        for error in result["errors"]
    )


def test_validate_contract_registry_accepts_gemini_kimi_host_rules(tmp_path: Path) -> None:
    fixture_root = tmp_path / "repo"
    (fixture_root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", fixture_root / "OMG_COMPAT_CONTRACT.md")
    shutil.copy2(ROOT / "registry" / "omg-capability.schema.json", fixture_root / "registry" / "omg-capability.schema.json")
    shutil.copytree(ROOT / "registry" / "bundles", fixture_root / "registry" / "bundles")

    control_plane_path = fixture_root / "registry" / "bundles" / "control-plane.yaml"
    control_plane = yaml.safe_load(control_plane_path.read_text(encoding="utf-8"))
    assert isinstance(control_plane, dict)
    control_plane["hosts"] = list(CANONICAL_HOSTS)
    host_rules = control_plane["policy_model"]["host_rules"]
    host_rules["gemini"] = {
        "compilation_targets": [".gemini/settings.json"],
        "mcp": ["omg-control"],
        "skills": ["omg/control-plane"],
        "automations": ["contract-validate"],
    }
    host_rules["kimi"] = {
        "compilation_targets": [".kimi/mcp.json"],
        "mcp": ["omg-control"],
        "skills": ["omg/control-plane"],
        "automations": ["contract-validate"],
    }
    dumped = yaml.safe_dump(control_plane, sort_keys=False)
    assert isinstance(dumped, str)
    control_plane_path.write_text(dumped, encoding="utf-8")

    result = validate_contract_registry(fixture_root)

    assert not [error for error in result["errors"] if "gemini" in error or "kimi" in error]


def test_validate_contract_registry_rejects_incomplete_gemini_host_rules(tmp_path: Path) -> None:
    fixture_root = tmp_path / "repo"
    (fixture_root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", fixture_root / "OMG_COMPAT_CONTRACT.md")
    shutil.copy2(ROOT / "registry" / "omg-capability.schema.json", fixture_root / "registry" / "omg-capability.schema.json")
    shutil.copytree(ROOT / "registry" / "bundles", fixture_root / "registry" / "bundles")

    control_plane_path = fixture_root / "registry" / "bundles" / "control-plane.yaml"
    control_plane = yaml.safe_load(control_plane_path.read_text(encoding="utf-8"))
    assert isinstance(control_plane, dict)
    control_plane["hosts"] = [host for host in CANONICAL_HOSTS if host != "kimi"]
    host_rules = control_plane["policy_model"]["host_rules"]
    host_rules["gemini"] = {
        "skills": ["omg/control-plane"],
        "automations": ["contract-validate"],
    }
    dumped = yaml.safe_dump(control_plane, sort_keys=False)
    assert isinstance(dumped, str)
    control_plane_path.write_text(dumped, encoding="utf-8")

    result = validate_contract_registry(fixture_root)

    assert result["status"] == "error"
    assert any(
        error == "control-plane: malformed host_rules entry for gemini: missing 'compilation_targets'"
        for error in result["errors"]
    )
    assert any(
        error == "control-plane: malformed host_rules entry for gemini: missing 'mcp'"
        for error in result["errors"]
    )


def test_compile_contract_outputs_writes_canonical_hosts_and_dist_artifacts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="enterprise",
    )

    assert result["schema"] == "OmgContractCompileResult"
    assert result["status"] == "ok"

    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    skill_path = tmp_path / ".agents" / "skills" / "omg" / "control-plane" / "SKILL.md"
    skill_meta_path = tmp_path / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml"
    gemini_path = tmp_path / ".gemini" / "settings.json"
    kimi_path = tmp_path / ".kimi" / "mcp.json"
    dist_manifest = tmp_path / "dist" / "enterprise" / "manifest.json"

    assert plugin_path.exists()
    assert skill_path.exists()
    assert skill_meta_path.exists()
    assert gemini_path.exists()
    assert kimi_path.exists()
    assert dist_manifest.exists()

    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert plugin["name"] == "omg"
    assert plugin["version"] == CANONICAL_VERSION

    manifest = json.loads(dist_manifest.read_text(encoding="utf-8"))
    assert manifest["channel"] == "enterprise"
    assert manifest["contract_version"] == CANONICAL_VERSION
    output_paths = {entry["path"] for entry in manifest["artifacts"]}
    assert "bundle/.claude-plugin/plugin.json" in output_paths
    assert "bundle/.agents/skills/omg/control-plane/SKILL.md" in output_paths
    assert "bundle/.gemini/settings.json" in output_paths
    assert "bundle/.kimi/mcp.json" in output_paths
    assert "bundle/.agents/skills/omg/plan-council/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/security-check/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/tracebank/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/remote-supervisor/SKILL.md" in output_paths


@pytest.mark.parametrize("host", CANONICAL_HOSTS)
def test_compile_contract_outputs_writes_per_host_artifacts(tmp_path: Path, host: str) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=[host],
        channel="public",
    )

    assert result["status"] == "ok"
    required_artifacts = {
        "claude": [tmp_path / "settings.json", tmp_path / ".claude-plugin" / "plugin.json"],
        "codex": [tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"],
        "gemini": [tmp_path / ".gemini" / "settings.json"],
        "kimi": [tmp_path / ".kimi" / "mcp.json"],
    }
    for artifact_path in required_artifacts[host]:
        assert artifact_path.exists(), f"missing required artifact for {host}: {artifact_path}"

    if host == "gemini":
        gemini_payload = json.loads((tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8"))
        assert gemini_payload["mcpServers"]["omg-control"]["command"] == "python3"
        assert gemini_payload["mcpServers"]["omg-control"]["args"] == ["-m", "runtime.omg_mcp_server"]

    if host == "kimi":
        kimi_payload = json.loads((tmp_path / ".kimi" / "mcp.json").read_text(encoding="utf-8"))
        assert kimi_payload["mcpServers"]["omg-control"]["command"] == "python3"
        assert kimi_payload["mcpServers"]["omg-control"]["args"] == ["-m", "runtime.omg_mcp_server"]


def test_compile_contract_outputs_embeds_phase1_release_audit_contract_for_all_hosts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )

    assert result["status"] == "ok"

    claude_settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    gemini_settings = json.loads((tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    kimi_settings = json.loads((tmp_path / ".kimi" / "mcp.json").read_text(encoding="utf-8"))
    codex_agents = (tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md").read_text(encoding="utf-8")

    for host_payload in (claude_settings, gemini_settings, kimi_settings):
        generated = host_payload["_omg"]["generated"]
        release_contract = generated["phase1_release_contract"]
        assert sorted(release_contract["forge_specialist_surfaces"]) == [
            "forge-profile-review",
            "forge-release-audit",
            "forge-validate",
        ]
        assert sorted(release_contract["release_surfaces"]) == [
            "OMG:profile-review",
            "OMG:release-audit",
            "OMG:validate",
        ]
        assert sorted(release_contract["release_readiness_checks"]) == [
            "claim_judge",
            "compliance_governor",
            "execution_primitives",
        ]
        assert sorted(release_contract["attestation_requirements"]) == [
            "registry.verify_artifact.sign_artifact_statement",
            "registry.verify_artifact.verify_artifact_statement",
        ]
        assert sorted(release_contract["compliance_governor_expectations"]) == [
            "runtime.compliance_governor.evaluate_release_compliance",
            "runtime.compliance_governor.evaluate_tool_compliance",
        ]

    assert "## Release Audit" in codex_agents
    assert "claim_judge" in codex_agents
    assert "compliance_governor" in codex_agents


def test_release_readiness_blocks_missing_gemini_host_artifact(tmp_path: Path, monkeypatch) -> None:
    _patch_fast_release_checks(monkeypatch)
    monkeypatch.setattr(
        contract_compiler_module,
        "_provider_statuses",
        lambda: {"gemini": {"ready": True, "source": "env"}},
    )

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=[host for host in CANONICAL_HOSTS if host != "kimi"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    gemini_path = tmp_path / ".gemini" / "settings.json"
    if gemini_path.exists():
        gemini_path.unlink()

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("provider_host_parity" in blocker and ".gemini/settings.json" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_failed_claim_judge_or_compliance_gate(tmp_path: Path, monkeypatch) -> None:
    _patch_fast_release_checks(monkeypatch)
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    monkeypatch.setattr(
        contract_compiler_module,
        "evaluate_release_compliance",
        lambda **_kwargs: {
            "status": "blocked",
            "authority": "claim_judge",
            "reason": "claim_judge_verdict=fail",
            "claim_judge_verdict": "fail",
        },
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert readiness["checks"]["claim_judge_compliance"]["status"] == "error"
    assert any("claim_judge_compliance_gate" in blocker for blocker in readiness["blockers"])


def test_codex_compile_marks_plan_council_as_explicit_invocation(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    skill_path = tmp_path / ".agents" / "skills" / "omg" / "plan-council" / "openai.yaml"
    agents_path = tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"

    assert skill_path.exists()
    assert "allow_implicit_invocation: false" in skill_path.read_text(encoding="utf-8")
    assert "plan-council" in agents_path.read_text(encoding="utf-8")


def test_dual_channel_bundles_keep_independent_hashes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    public_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    enterprise_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="enterprise",
    )

    assert public_result["status"] == "ok"
    assert enterprise_result["status"] == "ok"

    for channel in ("public", "enterprise"):
        dist_root = tmp_path / "dist" / channel
        manifest = json.loads((dist_root / "manifest.json").read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            artifact_path = dist_root / artifact["path"]
            assert artifact_path.exists()
            actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            assert actual_sha == artifact["sha256"]

        attestations = manifest.get("attestations")
        assert isinstance(attestations, list), "manifest must contain attestations array"
        assert len(attestations) == len(manifest["artifacts"])

        required_keys = {"artifact_path", "statement_path", "signature_path", "signer_key_id", "algorithm"}
        artifact_paths = {a["path"] for a in manifest["artifacts"]}
        for row in attestations:
            assert required_keys <= set(row), f"attestation row missing keys: {required_keys - set(row)}"
            assert row["artifact_path"] in artifact_paths
            assert row["algorithm"] == "ed25519-minisign"
            assert (dist_root / row["statement_path"]).exists()
            assert (dist_root / row["signature_path"]).exists()

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="dual")
    assert readiness["status"] == "ok"
    assert readiness["blockers"] == []


def test_release_readiness_rejects_cosmetic_evidence_and_eval_regressions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "run-1.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-1",
                "tests": [{"name": "pytest", "passed": True}],
                "security_scans": [],
                "diff_summary": {"files": 2},
                "reproducibility": {"cmd": "pytest -q"},
                "unresolved_risks": [],
                "provenance": [],
                "trust_scores": {},
                "api_twin": {},
                "lineage": {},
            }
        ),
        encoding="utf-8",
    )

    eval_root = tmp_path / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "status": "fail",
                "summary": {"regressed": True},
            }
        ),
        encoding="utf-8",
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("cosmetic evidence" in blocker for blocker in readiness["blockers"])
    assert any("eval regression" in blocker for blocker in readiness["blockers"])
    assert "security_blocker_unwaived" in readiness["checks"]


def test_release_readiness_security_blocker_unwaived_fails(tmp_path: Path, monkeypatch) -> None:
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
    (evidence_root / "run-1.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-1",
                "tests": [{"name": "worker_implementation", "passed": True}],
                "security_scans": [
                    {
                        "tool": "security-check",
                        "findings": [
                            {
                                "id": "B602",
                                "severity": "high",
                                "message": "shell=True detected",
                                "waived": False,
                            }
                        ],
                    }
                ],
                "diff_summary": {"files": 1},
                "reproducibility": {"cmd": "pytest -q"},
                "unresolved_risks": [],
                "provenance": [{"source": "security-check"}],
                "trust_scores": {"overall": 0.6},
                "api_twin": {},
                "trace_ids": ["trace-1"],
                "lineage": {"lineage_id": "lineage-1"},
                "timestamp": "2026-01-01T00:00:00+00:00",
                "executor": {"user": "ci", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "darwin"},
            }
        ),
        encoding="utf-8",
    )

    eval_root = tmp_path / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "status": "ok",
                "summary": {"regressed": False},
            }
        ),
        encoding="utf-8",
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("security_blocker_unwaived" in blocker for blocker in readiness["blockers"])
    assert readiness["checks"]["security_blocker_unwaived"]["status"] == "error"


def test_version_drift_blocker_on_plugin_mismatch(tmp_path: Path, monkeypatch) -> None:
    """Verify that a version mismatch in a plugin file triggers a named blocker."""
    import shutil
    
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    
    plugin_path = tmp_path / "plugins" / "advanced" / "plugin.json"
    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    
    plugin_data = {
        "name": "omg-advanced",
        "version": "1.0.0",
        "description": "Test plugin with mismatched version",
        "type": "omg-plugin",
        "commands": {}
    }
    plugin_path.write_text(json.dumps(plugin_data, indent=2), encoding="utf-8")
    
    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "run-1.json").write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "run-1",
                "tests": [{"name": "worker_implementation", "passed": True}],
                "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check.json"}],
                "diff_summary": {"files": 1},
                "reproducibility": {"cmd": "pytest -q"},
                "unresolved_risks": [],
                "provenance": [{"source": "security-check"}],
                "trust_scores": {"overall": 1.0},
                "api_twin": {},
                "trace_ids": ["trace-1"],
                "lineage": {"lineage_id": "lineage-1"},
            }
        ),
        encoding="utf-8",
    )
    
    eval_root = tmp_path / ".omg" / "evals"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / "latest.json").write_text(
        json.dumps(
            {
                "schema": "EvalGateResult",
                "status": "ok",
                "summary": {"regressed": False},
            }
        ),
        encoding="utf-8",
    )
    
    readiness = build_release_readiness(root_dir=tmp_path, output_root=tmp_path, channel="public")
    
    assert readiness["status"] == "error"
    version_drift_blockers = [b for b in readiness["blockers"] if "version_drift" in b]
    assert len(version_drift_blockers) > 0, "Expected at least one version_drift blocker"
    assert any("plugins/advanced/plugin.json" in b for b in version_drift_blockers), \
        f"Expected blocker mentioning plugins/advanced/plugin.json, got: {version_drift_blockers}"


def test_release_readiness_blocks_missing_doctor_linkage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("doctor_check_missing" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_missing_proof_chain_linkage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=False, include_attribution=True)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("proof_chain_linkage" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_missing_evidence_attribution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=False)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("missing_attribution" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_unwaived_high_risk_security(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(
        tmp_path,
        include_lineage=True,
        include_attribution=True,
        unresolved_risks=[{"severity": "high", "reason": "open finding"}],
    )
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("security_blocker_unwaived" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_stale_music_omr_daily_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    stale_music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    stale_music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.0.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-stale-music-omr",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    stale_music_evidence_path.write_text(json.dumps(stale_music_evidence, indent=2), encoding="utf-8")
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    os.utime(stale_music_evidence_path, (stale_ts, stale_ts))

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(
        "stale_execution_primitive: music_omr_testbed_evidence" in blocker
        for blocker in readiness["blockers"]
    )


def test_release_readiness_blocks_music_omr_run_id_linkage_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-linkage-mismatch",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-2",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    music_evidence_path.write_text(json.dumps(music_evidence, indent=2), encoding="utf-8")

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(
        "invalid_execution_primitive: music_omr_testbed_evidence: run_id_linkage_mismatch" in blocker
        for blocker in readiness["blockers"]
    )


def test_release_readiness_blocks_music_omr_payload_freshness_stale(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-freshness-stale",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-1",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    music_evidence_path.write_text(json.dumps(music_evidence, indent=2), encoding="utf-8")
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(music_evidence_path, (fresh_ts, fresh_ts))

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(
        "invalid_execution_primitive: music_omr_testbed_evidence: payload_freshness_stale" in blocker
        for blocker in readiness["blockers"]
    )


def test_release_readiness_passes_music_omr_with_fresh_evidence_and_matching_linkage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-fresh-linkage-ok",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-1",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    music_evidence_path.write_text(json.dumps(music_evidence, indent=2), encoding="utf-8")

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] in {"ok", "error"}
    assert not any(
        "music_omr_testbed_evidence" in blocker
        and (
            "run_id_linkage_mismatch" in blocker
            or "payload_freshness_stale" in blocker
        )
        for blocker in readiness["blockers"]
    )


def test_release_readiness_blocks_music_omr_coordinator_run_id_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    monkeypatch.setattr(contract_compiler_module, "is_release_orchestration_active", lambda project_dir: True)
    monkeypatch.setattr(contract_compiler_module, "get_active_coordinator_run_id", lambda _project_dir: "run-1")

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "coordinator_run_id": "run-2",
        "trace": {
            "trace_id": "trace-coordinator-mismatch",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-1",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    music_evidence_path.write_text(json.dumps(music_evidence, indent=2), encoding="utf-8")

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(
        "invalid_execution_primitive: music_omr_testbed_evidence: coordinator_run_id_mismatch" in blocker
        for blocker in readiness["blockers"]
    )


def test_release_readiness_keeps_music_omr_backward_compat_without_coordinator_run_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    monkeypatch.setattr(contract_compiler_module, "is_release_orchestration_active", lambda project_dir: True)
    monkeypatch.setattr(contract_compiler_module, "get_active_coordinator_run_id", lambda _project_dir: "run-1")

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    music_evidence_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-coordinator-backward-compat",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-1",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    music_evidence_path.write_text(json.dumps(music_evidence, indent=2), encoding="utf-8")

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert not any("coordinator_run_id_mismatch" in blocker for blocker in readiness["blockers"])


def test_release_readiness_uses_tracked_music_omr_fallback_when_primary_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    tracked_music_path = tmp_path / "artifacts" / "release" / "evidence" / "music-omr-run-1.json"
    tracked_music_path.parent.mkdir(parents=True, exist_ok=True)
    tracked_music_evidence = {
        "schema": "MusicOMREvidence",
        "schema_version": "2.1.0",
        "run_id": "run-1",
        "trace": {
            "trace_id": "trace-tracked-fallback",
            "gate": "music-omr-daily",
            "run_scope": "release-run",
        },
        "trace_metadata": {
            "testbed": "MusicOMRTestbed",
            "run_id_linkage": "run-1",
        },
        "fixture_inventory": ["simple_c_major.json", "transposition_pressure_fixture.json"],
        "freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_age_seconds": 86400,
        },
        "results": {"pressure": {"deterministic": True}},
    }
    tracked_music_path.write_text(json.dumps(tracked_music_evidence, indent=2), encoding="utf-8")

    primary_music_path = tmp_path / ".omg" / "evidence" / "music-omr-run-1.json"
    if primary_music_path.exists():
        primary_music_path.unlink()

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert not any(
        blocker == "missing_execution_primitive: music_omr_testbed_evidence" for blocker in readiness["blockers"]
    )
    primitives = readiness["checks"]["execution_primitives"]
    assert primitives["evidence_paths"]["music_omr_testbed_evidence"] == "artifacts/release/evidence/music-omr-run-1.json"


def test_release_readiness_blocks_prose_only_proof_claims(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    proof_root = tmp_path / "proof-root"
    shutil.copytree(ROOT / "registry", proof_root / "registry")
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", proof_root / "OMG_COMPAT_CONTRACT.md")
    (proof_root / ".git").mkdir(parents=True, exist_ok=True)
    (proof_root / "docs").mkdir(parents=True, exist_ok=True)
    (proof_root / "docs" / "proof.md").write_text(
        "# Proof\n\nAll 42 tests passed and 2/2 providers are green.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root: {"status": "ok", "errors": [], "bundles": [], "contract": {}},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_version_identity_drift",
        lambda _root: {"status": "ok", "blockers": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_release_surface_drift",
        lambda _root, _output: {"status": "ok", "blockers": [], "checks": {}},
    )

    readiness = build_release_readiness(root_dir=proof_root, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("prose_only_proof" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_non_loopback_http_production_claim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    scope_root = tmp_path / "scope-root"
    shutil.copytree(ROOT / "registry", scope_root / "registry")
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", scope_root / "OMG_COMPAT_CONTRACT.md")
    shutil.copy2(ROOT / "README.md", scope_root / "README.md")
    shutil.copy2(ROOT / "CHANGELOG.md", scope_root / "CHANGELOG.md")
    shutil.copy2(ROOT / "package.json", scope_root / "package.json")
    shutil.copy2(ROOT / "pyproject.toml", scope_root / "pyproject.toml")
    shutil.copy2(ROOT / "settings.json", scope_root / "settings.json")
    (scope_root / "plugins" / "core").mkdir(parents=True, exist_ok=True)
    (scope_root / "plugins" / "advanced").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "plugins" / "core" / "plugin.json", scope_root / "plugins" / "core" / "plugin.json")
    shutil.copy2(ROOT / "plugins" / "advanced" / "plugin.json", scope_root / "plugins" / "advanced" / "plugin.json")
    (scope_root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / ".claude-plugin" / "plugin.json", scope_root / ".claude-plugin" / "plugin.json")
    shutil.copy2(ROOT / ".claude-plugin" / "marketplace.json", scope_root / ".claude-plugin" / "marketplace.json")
    (scope_root / "docs").mkdir(parents=True, exist_ok=True)
    (scope_root / "docs" / "proof.md").write_text(
        "Production endpoint: http://10.0.0.8:8765/mcp\n",
        encoding="utf-8",
    )
    (scope_root / ".git").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root: {"status": "ok", "errors": [], "bundles": [], "contract": {}},
    )

    readiness = build_release_readiness(root_dir=scope_root, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("same_machine_scope_violation" in blocker for blocker in readiness["blockers"])


def test_claude_compile_includes_required_hooks_and_subagents(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))

    for event in REQUIRED_CLAUDE_HOOK_EVENTS:
        assert event in settings["hooks"], f"Missing hook event: {event}"
        assert len(settings["hooks"][event]) > 0, f"Empty registrations for {event}"

    subagents = settings["_omg"]["generated"]["subagents"]
    names = {sa["name"] for sa in subagents}
    expected_agents = {"architect-planner", "explorer-indexer", "implementer", "security-reviewer", "verifier", "causal-tracer"}
    for expected in expected_agents:
        assert expected in names, f"Missing governed agent: {expected}"

    for sa in subagents:
        assert sa.get("bypassPermissions") is not True, f"{sa['name']} has bypassPermissions"

    reviewer = next(sa for sa in subagents if sa["name"] == "security-reviewer")
    assert "Read" in reviewer["tools"]
    assert "Write" not in reviewer["tools"]

    implementer = next(sa for sa in subagents if sa["name"] == "implementer")
    assert "Write" in implementer["tools"]
    assert "protectedPaths" in implementer

    skills = settings["_omg"]["generated"]["skills"]
    assert len(skills) >= 1


def test_claude_compile_rejects_missing_required_hook(tmp_path: Path) -> None:
    settings = {
        "hooks": {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo ok"}]}],
        },
        "_omg": {
            "generated": {
                "subagents": [
                    {"name": "security-reviewer", "bypassPermissions": False},
                    {"name": "release-manager", "bypassPermissions": False},
                ],
            },
        },
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    errors = _validate_compiled_claude_output(tmp_path)
    assert len(errors) > 0
    missing_events = {e for e in REQUIRED_CLAUDE_HOOK_EVENTS if e != "PreToolUse"}
    for event in missing_events:
        assert any(event in err for err in errors), f"Expected error for missing {event}"


def test_claude_compile_fails_on_broken_hook_defaults(tmp_path: Path, monkeypatch) -> None:
    from runtime import contract_compiler

    original_fn = contract_compiler._default_claude_hook_registrations

    def broken_defaults():
        d = original_fn()
        d["InstructionsLoaded"] = []
        return d

    monkeypatch.setattr(contract_compiler, "_default_claude_hook_registrations", broken_defaults)

    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude"],
        channel="enterprise",
    )
    assert result["status"] == "error"
    assert any("InstructionsLoaded" in e for e in result["errors"])


def test_codex_compile_includes_all_agents_fragment_sections(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    agents_path = tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
    assert agents_path.exists()
    content = agents_path.read_text(encoding="utf-8")

    for section in REQUIRED_CODEX_AGENTS_SECTIONS:
        assert section in content, f"Missing section: {section}"

    assert "python3 -m pytest tests -q" in content
    assert "prefer_cached" in content or "cached" in content.lower()
    assert "Destructive" in content or "approval" in content.lower()
    assert ".omg/**" in content


def test_codex_compile_produces_rules_fragment(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    rules_path = tmp_path / ".agents" / "skills" / "omg" / "codex-rules.md"
    assert rules_path.exists()
    content = rules_path.read_text(encoding="utf-8")

    assert "cached_web_search: prefer_cached" in content
    assert "live_network: deny_by_default" in content
    assert "destructive_approval: required" in content
    assert "omg/control-plane" in content


def test_codex_compile_includes_skills_and_evidence(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    agents_path = tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
    content = agents_path.read_text(encoding="utf-8")

    assert "omg/control-plane" in content
    assert "omg/mcp-fabric" in content

    assert "timestamp" in content
    assert "executor" in content
    assert "trace_id" in content
    assert "lineage" in content


def test_codex_compile_rejects_missing_agents_section(tmp_path: Path) -> None:
    shared_dir = tmp_path / ".agents" / "skills" / "omg"
    shared_dir.mkdir(parents=True, exist_ok=True)

    (shared_dir / "AGENTS.fragment.md").write_text(
        "# Minimal\n\nNo sections here.\n",
        encoding="utf-8",
    )
    (shared_dir / "codex-rules.md").write_text("# Rules\n", encoding="utf-8")
    (shared_dir / "codex-mcp.toml").write_text("[servers]\n", encoding="utf-8")

    errors = _validate_compiled_codex_output(tmp_path)
    assert len(errors) > 0
    missing_sections = {s for s in REQUIRED_CODEX_AGENTS_SECTIONS if s != "## Build & Test"}
    for section in missing_sections:
        assert any(section in err for err in errors), f"Expected error for missing {section}"


def test_codex_compile_rejects_missing_required_outputs(tmp_path: Path) -> None:
    shared_dir = tmp_path / ".agents" / "skills" / "omg"
    shared_dir.mkdir(parents=True, exist_ok=True)

    (shared_dir / "AGENTS.fragment.md").write_text("# Stub\n", encoding="utf-8")

    errors = _validate_compiled_codex_output(tmp_path)
    assert any("codex-rules.md" in err for err in errors)
    assert any("codex-mcp.toml" in err for err in errors)


def test_codex_compile_fails_on_stripped_agents_fragment(tmp_path: Path, monkeypatch) -> None:
    from runtime import contract_compiler

    original_fn = contract_compiler._render_codex_agents_fragment

    def stripped_renderer(**kwargs):
        return "# OMG Codex Governance\n\nStripped content with no sections.\n"

    monkeypatch.setattr(contract_compiler, "_render_codex_agents_fragment", stripped_renderer)

    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "error"
    assert any("AGENTS.fragment.md" in e for e in result["errors"])


def test_compile_includes_advanced_plugin_artifacts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert result["status"] == "ok"

    manifest_path = tmp_path / "dist" / "public" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_paths = {a["path"] for a in manifest["artifacts"]}

    for req in _get_required_advanced_plugin_artifacts(ROOT):
        assert req in manifest_paths, f"Missing required advanced artifact: {req}"


def test_advanced_artifact_manifest_derived_requirements() -> None:
    required = _get_required_advanced_plugin_artifacts(ROOT)
    manifest = json.loads((ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8"))
    expected = {
        "bundle/plugins/advanced/plugin.json",
        *[
            f"bundle/plugins/advanced/{cmd['path'].replace(':', '-')}"
            for cmd in manifest["commands"].values()
            if isinstance(cmd, dict) and isinstance(cmd.get("path"), str)
        ],
    }

    assert set(required) == expected
    assert "bundle/plugins/advanced/commands/OMG-security-review.md" not in required
    assert len(required) == 10


def test_advanced_command_path_integrity(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert result["status"] == "ok"

    bundle_root = tmp_path / "dist" / "public" / "bundle"
    plugin_json_path = bundle_root / "plugins" / "advanced" / "plugin.json"
    assert plugin_json_path.exists()

    plugin_data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    commands = plugin_data.get("commands", {})
    assert len(commands) > 0

    for cmd_name, cmd_info in commands.items():
        cmd_rel_path = cmd_info.get("path", "").replace(":", "-")
        cmd_full_path = plugin_json_path.parent / cmd_rel_path
        assert cmd_full_path.exists(), (
            f"Command '{cmd_name}' references '{cmd_rel_path}' which is missing from bundle"
        )


def test_release_readiness_blocks_missing_advanced_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    manifest_path = tmp_path / "dist" / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = [
        a for a in manifest["artifacts"]
        if not str(a.get("path", "")).startswith("bundle/plugins/advanced/")
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("advanced_plugin_missing" in b for b in readiness["blockers"])


def test_release_readiness_plugin_command_security_review_not_required(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "ok"
    assert all("OMG:security-review.md" not in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_missing_manifest_declared_advanced_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    manifest_path = tmp_path / "dist" / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_path = "bundle/plugins/advanced/commands/OMG-learn.md"
    manifest["artifacts"] = [a for a in manifest["artifacts"] if str(a.get("path", "")) != missing_path]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(f"advanced_plugin_missing {missing_path}" in b for b in readiness["blockers"])


def test_release_readiness_blocks_missing_proof_gate_claims(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True, include_claims=False)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert readiness["checks"]["proof_chain"]["proof_gate"]["verdict"] == "fail"
    assert any("proof_gate_blocked" in blocker for blocker in readiness["blockers"])


def test_release_readiness_execution_primitives_pin_release_requirements(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    execution_primitives = readiness["checks"]["execution_primitives"]
    assert execution_primitives["evidence_profile"] == "release"
    assert execution_primitives["required_evidence_requirements"] == requirements_for_profile("release")


def test_execution_primitives_missing_profile_fails_closed_to_full_requirements(tmp_path: Path) -> None:
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    payload_path = tmp_path / ".omg" / "evidence" / "run-1.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload.pop("evidence_profile", None)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    result = contract_compiler_module._check_execution_primitives(output_root=tmp_path)

    assert result["required_evidence_requirements"] == requirements_for_profile(None)
    assert any(item.startswith("missing_execution_primitive:") for item in result["blockers"])


def test_execution_primitives_blocks_cross_run_evidence_pack(tmp_path: Path) -> None:
    stale_run_id = "stale-run-456"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    evidence_path = tmp_path / ".omg" / "evidence" / "run-1.json"
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_payload["run_id"] = stale_run_id
    evidence_payload["context_checksum"] = f"ctx-{stale_run_id}"
    evidence_path.write_text(json.dumps(evidence_payload), encoding="utf-8")
    _write_execution_primitives(tmp_path, run_id=stale_run_id)

    with patch("runtime.contract_compiler.get_active_coordinator_run_id", return_value="active-run-123"):
        result = contract_compiler_module._check_execution_primitives(output_root=tmp_path)

    assert "execution_primitive:cross_run" in result["blockers"]


def test_release_readiness_blocks_stale_exec_kernel_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    evidence_path = tmp_path / ".omg" / "evidence" / "run-1.json"
    exec_kernel_path = tmp_path / ".omg" / "state" / "exec-kernel" / "run-1.json"
    stale_mtime = max(1.0, evidence_path.stat().st_mtime - 7200.0)
    os.utime(exec_kernel_path, (stale_mtime, stale_mtime))

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("stale_execution_primitive: exec_kernel_state" in blocker for blocker in readiness["blockers"])


def test_release_readiness_blocks_synthetic_host_parity_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    host_parity_path = tmp_path / ".omg" / "evidence" / "host-parity-run-1.json"
    host_parity = json.loads(host_parity_path.read_text(encoding="utf-8"))
    host_parity["parity_results"]["host_results"]["codex"]["normalized"]["source_class"] = "synthetic"
    host_parity["parity_results"]["host_results"]["codex"]["normalized"]["source_path"] = ""
    host_parity_path.write_text(json.dumps(host_parity), encoding="utf-8")

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any(
        "host_semantic_parity: synthetic payload rejected for codex" in blocker
        for blocker in readiness["blockers"]
    )


def test_release_readiness_blocks_excluded_failures_without_signed_waiver(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    evidence_path = tmp_path / ".omg" / "evidence" / "run-1.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["excluded_failures"] = [
        {
            "id": "pytest::test_flaky_release_gate",
            "reason": "known deterministic fixture",
        }
    ]
    payload.pop("excluded_failures_waiver_path", None)
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("excluded_failures_without_signed_waiver" in blocker for blocker in readiness["blockers"])


def test_release_readiness_dual_bundle_promotion_parity_happy_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root=None: {
            "schema": "OmgContractValidationResult",
            "status": "ok",
            "errors": [],
            "contract": {},
            "bundles": [],
        },
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_version_identity_drift",
        lambda _root: {
            "status": "ok",
            "canonical_version": "",
            "blockers": [],
            "drift_details": {},
        },
    )
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    public_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    enterprise_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="enterprise",
    )
    assert public_result["status"] == "ok"
    assert enterprise_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="dual")

    assert readiness["status"] == "ok", readiness["blockers"]
    assert readiness["checks"]["bundle_promotion_parity"]["status"] == "ok"
    assert "bundle_promotion_parity" not in readiness["blockers"]


def test_release_readiness_dual_bundle_promotion_parity_blocks_missing_dist_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root=None: {
            "schema": "OmgContractValidationResult",
            "status": "ok",
            "errors": [],
            "contract": {},
            "bundles": [],
        },
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_version_identity_drift",
        lambda _root: {
            "status": "ok",
            "canonical_version": "",
            "blockers": [],
            "drift_details": {},
        },
    )
    _patch_fast_release_checks(monkeypatch)

    public_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    enterprise_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="enterprise",
    )
    assert public_result["status"] == "ok"
    assert enterprise_result["status"] == "ok"

    missing_skill = (
        tmp_path
        / "dist"
        / "public"
        / "bundle"
        / ".agents"
        / "skills"
        / "omg"
        / "proof-gate"
        / "SKILL.md"
    )
    missing_skill.unlink()

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="dual")

    assert readiness["status"] == "error"
    assert "bundle_promotion_parity" in readiness["blockers"]
    assert str(missing_skill.relative_to(tmp_path)) in readiness["checks"]["bundle_promotion_parity"]["missing_dist_public"]


def test_default_required_bundles_includes_all_truth_council_bundles() -> None:
    for bundle_id in TRUTH_COUNCIL_BUNDLES:
        assert bundle_id in DEFAULT_REQUIRED_BUNDLES, (
            f"Truth/council bundle '{bundle_id}' missing from DEFAULT_REQUIRED_BUNDLES"
        )


def test_compiled_settings_includes_truth_council_required_bundles(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    required_bundles = settings["_omg"]["generated"]["required_bundles"]
    for bundle_id in TRUTH_COUNCIL_BUNDLES:
        assert bundle_id in required_bundles, (
            f"Truth/council bundle '{bundle_id}' missing from compiled settings.json required_bundles"
        )


def test_compiled_manifest_includes_truth_council_bundle_skills(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert result["status"] == "ok"

    manifest = json.loads(
        (tmp_path / "dist" / "public" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_paths = {a["path"] for a in manifest["artifacts"]}
    for bundle_id in TRUTH_COUNCIL_BUNDLES:
        expected_path = f"bundle/.agents/skills/omg/{bundle_id}/SKILL.md"
        assert expected_path in manifest_paths, (
            f"Manifest missing SKILL.md artifact for truth/council bundle '{bundle_id}'"
        )


def test_protected_planning_surface_renders_council_bundles(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    agents_content = (
        tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
    ).read_text(encoding="utf-8")
    assert "## Protected Planning Surface" in agents_content
    assert "omg/plan-council" in agents_content


def test_removing_truth_council_bundle_from_constant_fails_parity(
    tmp_path: Path, monkeypatch
) -> None:
    stripped = tuple(b for b in DEFAULT_REQUIRED_BUNDLES if b != "claim-judge")
    monkeypatch.setattr(contract_compiler_module, "DEFAULT_REQUIRED_BUNDLES", stripped)

    with pytest.raises(AssertionError, match="claim-judge"):
        for bundle_id in TRUTH_COUNCIL_BUNDLES:
            assert bundle_id in contract_compiler_module.DEFAULT_REQUIRED_BUNDLES, (
                f"Truth/council bundle '{bundle_id}' missing from DEFAULT_REQUIRED_BUNDLES"
            )


def _seed_package_parity_surface_fixture(root: Path) -> None:
    required_surfaces = ("hash-edit", "ast-pack", "terminal-lane")
    for surface in required_surfaces:
        source_skill = root / ".agents" / "skills" / "omg" / surface / "SKILL.md"
        source_skill.parent.mkdir(parents=True, exist_ok=True)
        source_skill.write_text(f"# {surface}\n", encoding="utf-8")

        dist_skill = root / "dist" / "public" / "bundle" / ".agents" / "skills" / "omg" / surface / "SKILL.md"
        dist_skill.parent.mkdir(parents=True, exist_ok=True)
        dist_skill.write_text(f"# {surface}\n", encoding="utf-8")

        release_skill = (
            root
            / "artifacts"
            / "release"
            / "dist"
            / "public"
            / "bundle"
            / ".agents"
            / "skills"
            / "omg"
            / surface
            / "SKILL.md"
        )
        release_skill.parent.mkdir(parents=True, exist_ok=True)
        release_skill.write_text(f"# {surface}\n", encoding="utf-8")

    wheel_path = root / "dist" / "fixture-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, mode="w") as archive:
        for surface in required_surfaces:
            archive.writestr(f"pkg/.agents/skills/omg/{surface}/SKILL.md", f"# {surface}\n")


def test_check_package_parity_accepts_all_required_surface_locations(tmp_path: Path) -> None:
    _seed_package_parity_surface_fixture(tmp_path)

    result = check_package_parity(tmp_path)

    assert result["status"] == "ok"
    assert result["blockers"] == []
    assert result["machine_blockers"] == []


def test_check_package_parity_reports_machine_readable_blocker_for_missing_surface(tmp_path: Path) -> None:
    _seed_package_parity_surface_fixture(tmp_path)
    missing_dist_surface = (
        tmp_path
        / "dist"
        / "public"
        / "bundle"
        / ".agents"
        / "skills"
        / "omg"
        / "terminal-lane"
        / "SKILL.md"
    )
    missing_dist_surface.unlink()

    result = check_package_parity(tmp_path)

    assert result["status"] == "error"
    assert any("surface=terminal-lane" in blocker for blocker in result["blockers"])
    assert any(
        blocker.get("location") == "dist" and blocker.get("surface") == "terminal-lane"
        for blocker in result["machine_blockers"]
        if isinstance(blocker, dict)
    )


def _setup_drift_fixture(fixture_root: Path) -> None:
    for f in ("package.json", "pyproject.toml", "settings.json", "CHANGELOG.md"):
        shutil.copy2(ROOT / f, fixture_root / f)
    for sub in ("plugins/core", "plugins/advanced", ".claude-plugin"):
        (fixture_root / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "plugins" / "core" / "plugin.json",
        fixture_root / "plugins" / "core" / "plugin.json",
    )
    shutil.copy2(
        ROOT / "plugins" / "advanced" / "plugin.json",
        fixture_root / "plugins" / "advanced" / "plugin.json",
    )
    shutil.copy2(
        ROOT / ".claude-plugin" / "plugin.json",
        fixture_root / ".claude-plugin" / "plugin.json",
    )
    shutil.copy2(
        ROOT / ".claude-plugin" / "marketplace.json",
        fixture_root / ".claude-plugin" / "marketplace.json",
    )


def test_version_drift_blocker_on_marketplace_nested_version_fields(
    tmp_path: Path,
) -> None:
    _setup_drift_fixture(tmp_path)

    marketplace_data = {
        "name": "omg",
        "version": CANONICAL_VERSION,
        "metadata": {
            "description": "OMG",
            "version": "0.0.0-stale",
            "homepage": "https://github.com/trac3er00/OMG",
            "repository": "https://github.com/trac3er00/OMG",
        },
        "plugins": [
            {
                "name": "omg",
                "description": "OMG plugin",
                "version": "0.0.0-stale",
                "source": "./",
                "author": {"name": "trac3er00"},
                "license": "MIT",
                "category": "productivity",
                "tags": [],
            }
        ],
    }
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace_data, indent=2), encoding="utf-8"
    )

    result = contract_compiler_module._check_version_identity_drift(tmp_path)

    blockers = result["blockers"]
    assert any("metadata" in b for b in blockers), (
        f"Expected blocker for marketplace.json metadata.version divergence, got: {blockers}"
    )
    assert any("plugins" in b for b in blockers), (
        f"Expected blocker for marketplace.json plugins[0].version divergence, got: {blockers}"
    )


def test_malformed_pyproject_toml_produces_explicit_parse_blocker(
    tmp_path: Path,
) -> None:
    _setup_drift_fixture(tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'oh-my-god'\nversion = '0.0.1-test'\n",
        encoding="utf-8",
    )

    result = contract_compiler_module._check_version_identity_drift(tmp_path)

    blockers = result["blockers"]
    pyproject_blockers = [b for b in blockers if "pyproject.toml" in b]
    assert len(pyproject_blockers) > 0, (
        f"Expected explicit parse blocker for malformed pyproject.toml, got: {blockers}"
    )
    assert any("<pattern not found>" in b for b in pyproject_blockers), (
        f"Malformed pyproject.toml must surface parser fallout from shared check_surface: {pyproject_blockers}"
    )


def test_version_drift_allows_missing_source_only_surface_in_package_layout(
    tmp_path: Path,
) -> None:
    for rel_path in get_authored_paths():
        if rel_path == ".claude-plugin/scripts/install.sh":
            continue
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel_path, target)

    result = contract_compiler_module._check_version_identity_drift(tmp_path)

    assert result["status"] == "ok"
    assert result["blockers"] == []


def test_version_drift_blocks_missing_source_only_surface_in_source_layout(
    tmp_path: Path,
) -> None:
    for rel_path in get_authored_paths():
        if rel_path == ".claude-plugin/scripts/install.sh":
            continue
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel_path, target)

    (tmp_path / ".git").mkdir()

    result = contract_compiler_module._check_version_identity_drift(tmp_path)

    assert result["status"] == "error"
    assert any(".claude-plugin/scripts/install.sh" in blocker for blocker in result["blockers"])


# ── Version identity drift integration with build_release_readiness ────────


def test_build_release_readiness_includes_version_identity_drift_section(
    tmp_path: Path, monkeypatch
) -> None:
    """build_release_readiness output must include a version_identity_drift check."""
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"
    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert "version_identity_drift" in readiness["checks"], (
        "build_release_readiness must include version_identity_drift in checks"
    )
    drift_check = readiness["checks"]["version_identity_drift"]
    assert "status" in drift_check
    assert "blockers" in drift_check


def test_build_release_readiness_drift_section_contains_blockers_on_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    """When version drift exists, version_identity_drift section must report blockers."""
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")

    # Patch all checks EXCEPT version drift — let that run live against tmp_path
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_packaged_install_smoke",
        lambda _root: {"status": "ok", "blockers": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "_check_mcp_fabric",
        lambda: {"ready": True, "prompt_count": 1, "resource_count": 1},
    )

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="public",
    )
    assert compile_result["status"] == "ok"

    # Set up a fixture root with a deliberately drifted version in package.json
    fixture_root = tmp_path / "drift-root"
    fixture_root.mkdir(parents=True, exist_ok=True)
    _setup_drift_fixture(fixture_root)
    (fixture_root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "OMG_COMPAT_CONTRACT.md", fixture_root / "OMG_COMPAT_CONTRACT.md")
    shutil.copy2(
        ROOT / "registry" / "omg-capability.schema.json",
        fixture_root / "registry" / "omg-capability.schema.json",
    )
    shutil.copytree(ROOT / "registry" / "bundles", fixture_root / "registry" / "bundles")
    (fixture_root / ".git").mkdir(parents=True, exist_ok=True)

    # Inject drift: package.json with wrong version
    pkg = json.loads((fixture_root / "package.json").read_text(encoding="utf-8"))
    pkg["version"] = "0.0.0-drifted"
    (fixture_root / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    # Stub registry validation for the fixture root
    monkeypatch.setattr(
        contract_compiler_module,
        "validate_contract_registry",
        lambda _root: {"status": "ok", "errors": [], "bundles": [], "contract": {}},
    )

    readiness = build_release_readiness(
        root_dir=fixture_root, output_root=tmp_path, channel="public"
    )

    assert readiness["status"] == "error"
    assert "version_identity_drift" in readiness["checks"]
    drift_section = readiness["checks"]["version_identity_drift"]
    assert len(drift_section["blockers"]) > 0, (
        f"Expected blockers in version_identity_drift section, got: {drift_section}"
    )
    assert any("package.json" in b for b in drift_section["blockers"]), (
        f"Expected package.json drift blocker, got: {drift_section['blockers']}"
    )


def test_contract_validate_release_identity_outputs_blocker_payloads(
    monkeypatch, capsys
) -> None:
    import scripts.omg as omg_cli

    class _StubValidator:
        @staticmethod
        def extract_canonical_version(_path):
            return CANONICAL_VERSION

        @staticmethod
        def validate_authored(_root, _canonical):
            return {
                "status": "fail",
                "blockers": [
                    {
                        "surface": "package.json version",
                        "found": "0.0.0",
                        "expected": CANONICAL_VERSION,
                    }
                ],
            }

        @staticmethod
        def validate_derived(_root, _canonical):
            return {"status": "ok", "blockers": []}

        @staticmethod
        def scan_scoped_residue(_root, _forbid_version):
            return {
                "status": "fail",
                "forbid_version": "2.1.0",
                "blockers": [
                    {
                        "file": "dist/public/manifest.json",
                        "line": 1,
                        "content": '"contract_version": "2.1.0"',
                    }
                ],
            }

        @staticmethod
        def build_report(**kwargs):
            return {
                "canonical_version": kwargs["canonical"],
                "scope": kwargs["scope"],
                "forbid_version": kwargs["forbid_version"],
                "authored": kwargs["authored"],
                "derived": kwargs["derived"],
                "scoped_residue": kwargs["scoped_residue"],
                "overall_status": "fail",
            }

    monkeypatch.setattr(
        omg_cli,
        "validate_contract_registry",
        lambda _root: {
            "schema": "OmgContractValidationResult",
            "status": "ok",
            "errors": [],
            "bundles": [],
            "contract": {},
        },
    )
    monkeypatch.setattr(omg_cli, "_load_release_identity_validator", lambda: _StubValidator())

    exit_code = omg_cli.cmd_contract_validate(
        argparse.Namespace(release_identity_scope="all", forbid_version="2.1.0")
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 2
    assert payload["status"] == "error"
    assert "release_identity" in payload
    assert payload["release_identity"]["overall_status"] == "fail"
    assert payload["release_identity"]["authored"]["blockers"][0]["surface"] == "package.json version"
    assert payload["release_identity"]["scoped_residue"]["blockers"][0]["file"] == "dist/public/manifest.json"


# --- validate integration tests ---


def test_validate_run_returns_structured_result():
    from runtime.validate import run_validate

    result = run_validate()
    assert result["schema"] == "ValidateResult"
    assert result["status"] in ("pass", "fail")
    assert isinstance(result["checks"], list)
    assert len(result["checks"]) > 0
    assert "version" in result


def test_validate_composes_doctor_checks():
    from runtime.validate import run_validate

    result = run_validate()
    check_names = {c["name"] for c in result["checks"]}
    # Doctor checks are composed in, not duplicated
    assert "python_version" in check_names


def test_validate_contract_check_present():
    from runtime.validate import run_validate

    result = run_validate()
    check_names = {c["name"] for c in result["checks"]}
    assert "contract_registry" in check_names


def test_validate_profile_check_present():
    from runtime.validate import run_validate

    result = run_validate()
    check_names = {c["name"] for c in result["checks"]}
    assert "profile_governor" in check_names


def test_validate_install_check_present():
    from runtime.validate import run_validate

    result = run_validate()
    check_names = {c["name"] for c in result["checks"]}
    assert "install_integrity" in check_names


def test_validate_check_fields_have_expected_shape():
    from runtime.validate import run_validate

    result = run_validate()
    for check in result["checks"]:
        assert "name" in check
        assert "status" in check
        assert check["status"] in ("ok", "blocker", "warning")
        assert "message" in check
        assert "required" in check


def test_validate_fail_status_when_blocker():
    from runtime.validate import run_validate

    result = run_validate()
    has_blocker = any(c["status"] == "blocker" for c in result["checks"])
    if has_blocker:
        assert result["status"] == "fail"
    else:
        assert result["status"] == "pass"


def _scaffold_plugin_tree(root: Path, *, missing_advanced_cmd: str | None = None) -> None:
    core_dir = root / "plugins" / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    core_commands_dir = root / "commands"
    core_commands_dir.mkdir(parents=True, exist_ok=True)

    core_manifest = {
        "commands": {
            "setup": {"path": "commands/OMG:setup.md"},
            "init": {"path": "commands/OMG:init.md"},
        }
    }
    (core_dir / "plugin.json").write_text(json.dumps(core_manifest), encoding="utf-8")
    (core_commands_dir / "OMG:setup.md").write_text("# setup\n", encoding="utf-8")
    (core_commands_dir / "OMG:init.md").write_text("# init\n", encoding="utf-8")

    adv_dir = root / "plugins" / "advanced"
    adv_commands_dir = adv_dir / "commands"
    adv_commands_dir.mkdir(parents=True, exist_ok=True)

    adv_manifest = {
        "commands": {
            "deep-plan": {"path": "commands/OMG:deep-plan.md"},
            "learn": {"path": "commands/OMG:learn.md"},
        }
    }
    (adv_dir / "plugin.json").write_text(json.dumps(adv_manifest), encoding="utf-8")

    for cmd_name in ("OMG:deep-plan.md", "OMG:learn.md"):
        if cmd_name == missing_advanced_cmd:
            continue
        (adv_commands_dir / cmd_name).write_text(f"# {cmd_name}\n", encoding="utf-8")


def test_plugin_command_paths_valid_tree(tmp_path: Path) -> None:
    _scaffold_plugin_tree(tmp_path)

    result = _check_plugin_command_paths(tmp_path)

    assert result["status"] == "ok"
    assert result["blockers"] == []
    assert result["details"]["core"]["status"] == "ok"
    assert result["details"]["advanced"]["status"] == "ok"


def test_plugin_command_paths_missing_source(tmp_path: Path) -> None:
    _scaffold_plugin_tree(tmp_path, missing_advanced_cmd="OMG:learn.md")

    result = _check_plugin_command_paths(tmp_path)

    assert result["status"] == "error"
    assert any("plugin_command_paths" in b for b in result["blockers"])
    assert any("missing source" in b for b in result["blockers"])
    assert any("learn" in b for b in result["blockers"])
    assert result["details"]["advanced"]["status"] == "error"
    assert result["details"]["core"]["status"] == "ok"


def test_contract_doc_does_not_contain_labs_as_channel() -> None:
    from runtime.contract_compiler import load_contract_doc
    doc = load_contract_doc(ROOT)
    
    # Find the release_channels section
    if "## release_channels" in doc:
        section = doc.split("## release_channels")[1].split("##")[0]
        assert "labs" not in section.lower(), "labs found in release_channels section"
    
    # General check for 'labs' as a channel label
    # We expect 'labs' to be mentioned as a preset, but not as a channel.
    # The contract now explicitly says "labs is a preset, not a release channel."
    # So we check if it's listed as a channel.
    lines = doc.splitlines()
    for line in lines:
        if "channel" in line.lower() and "labs" in line.lower():
            # It's okay if it says "labs is not a channel"
            if "not a" in line.lower() or "not as a" in line.lower():
                continue
            pytest.fail(f"Potential 'labs' as channel reference found: {line}")


# ── Release surface drift gate ──────────────────────────────────────────────


def _build_surface_drift_fixture(
    root: Path,
    output: Path,
    *,
    bin_key: str | None = None,
    action_yml: bool = True,
) -> None:
    from runtime.release_surface_registry import get_public_surfaces

    surfaces = get_public_surfaces()
    manifest = {
        "generated_by": "omg release compile-surfaces",
        "version": "2.2.8",
        "generated_at": "2025-01-01T00:00:00+00:00",
        "surfaces": surfaces,
    }
    manifest_dir = output / "dist" / "public"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "release-surface.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8",
    )

    pkg: dict[str, object] = {"name": "@trac3er/oh-my-god", "version": "2.2.8"}
    if bin_key is not None:
        pkg["bin"] = {bin_key: "./OMG-setup.sh"}
    (root / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    if action_yml:
        (root / "action.yml").write_text("name: OMG\n", encoding="utf-8")


def _stub_release_text_and_docs_clean(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_compiler_module,
        "compile_release_surfaces",
        lambda _root, check_only=False: {"status": "ok", "drift": []} if check_only else {"status": "ok", "artifacts": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "check_docs",
        lambda _root: {"status": "ok", "drift": []},
    )


def test_release_surface_drift_no_blockers_when_agreement(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="omg", action_yml=True)
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "ok"
    assert result["blockers"] == []
    assert "checks" in result


def test_release_surface_drift_blocks_missing_npm_bin(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key=None, action_yml=True)
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any("package.json missing npm bin.omg" in b for b in result["blockers"])


def test_release_surface_drift_blocks_missing_action_yml(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="omg", action_yml=False)
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any("action.yml not found" in b for b in result["blockers"])


def test_release_surface_drift_blocks_wrong_npm_bin_key(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="wrong-name", action_yml=True)
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any("package.json missing npm bin.omg" in b for b in result["blockers"])


def test_release_surface_drift_blocks_missing_manifest(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    (root / "package.json").write_text('{"name":"test","version":"1.0.0","bin":{"omg":"./x"}}')
    (root / "action.yml").write_text("name: OMG\n")
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any("release-surface.json" in b for b in result["blockers"])


def test_compile_contract_outputs_emits_release_surface_manifest(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )

    assert result["status"] == "ok"
    assert (tmp_path / "dist" / "public" / "release-surface.json").exists()


def test_release_surface_drift_uses_repo_manifest_when_output_manifest_missing(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, root, bin_key="omg", action_yml=True)
    _stub_release_text_and_docs_clean(monkeypatch)

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "ok"
    assert result["blockers"] == []


# ---------------------------------------------------------------------------
# _check_policy_pack_signatures
# ---------------------------------------------------------------------------


def test_check_policy_pack_signatures_non_enforcing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", raising=False)

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "ok"
    assert result["enforcing"] is False
    assert result["blockers"] == []


def test_check_policy_pack_signatures_enforcing_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", "1")
    packs_dir = tmp_path / "registry" / "policy-packs"
    packs_dir.mkdir(parents=True)
    for pack_id in ("locked-prod", "fintech", "airgapped"):
        (packs_dir / f"{pack_id}.yaml").write_text(f"id: {pack_id}\n")

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "error"
    assert result["enforcing"] is True
    assert len(result["blockers"]) == 3
    assert all("policy_pack_signature:" in b for b in result["blockers"])
    assert any("locked-prod" in b for b in result["blockers"])
    assert any("fintech" in b for b in result["blockers"])
    assert any("airgapped" in b for b in result["blockers"])


def test_check_policy_pack_signatures_enforcing_valid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", "1")
    packs_dir = tmp_path / "registry" / "policy-packs"
    packs_dir.mkdir(parents=True)

    digest = "a" * 64
    for pack_id in ("locked-prod", "fintech", "airgapped"):
        (packs_dir / f"{pack_id}.lock.json").write_text(
            json.dumps({"canonical_digest": digest})
        )
        (packs_dir / f"{pack_id}.signature.json").write_text(
            json.dumps({
                "artifact_digest": digest,
                "action": "policy-pack-sign",
                "scope": f"policy-pack/{pack_id}",
                "reason": "test",
                "signer_key_id": "test-key",
                "issued_at": "2026-01-01T00:00:00Z",
                "signature": "test-sig",
            })
        )

    monkeypatch.setattr(
        contract_compiler_module,
        "verify_approval_artifact",
        lambda approval, expected: {"valid": True, "reason": "verified"},
    )

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "ok"
    assert result["enforcing"] is True
    assert result["blockers"] == []


# ---------------------------------------------------------------------------
# _check_release_surface_drift: release-text and docs drift integration
# ---------------------------------------------------------------------------


def test_release_surface_drift_includes_release_text_drift_blockers(
    tmp_path: Path, monkeypatch
) -> None:
    """_check_release_surface_drift must call compile_release_surfaces(root, check_only=True)
    and propagate drift items as release_text_drift: blockers."""
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="omg", action_yml=True)

    monkeypatch.setattr(
        contract_compiler_module,
        "compile_release_surfaces",
        lambda _root, check_only=False: {
            "status": "drift",
            "drift": [
                {"surface": "changelog_current", "path": "CHANGELOG.md", "reason": "content drift in generated block"},
            ],
        } if check_only else {"status": "ok", "artifacts": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "check_docs",
        lambda _root: {"status": "ok", "drift": []},
    )

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any(b.startswith("release_text_drift:") for b in result["blockers"]), (
        f"Expected release_text_drift: blocker, got: {result['blockers']}"
    )


def test_release_surface_drift_includes_docs_drift_blockers(
    tmp_path: Path, monkeypatch
) -> None:
    """_check_release_surface_drift must call check_docs(root) and propagate
    drift items as docs_drift: blockers."""
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="omg", action_yml=True)

    monkeypatch.setattr(
        contract_compiler_module,
        "compile_release_surfaces",
        lambda _root, check_only=False: {"status": "ok", "drift": []} if check_only else {"status": "ok", "artifacts": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "check_docs",
        lambda _root: {"status": "drift", "drift": ["Missing: support-matrix.json"]},
    )

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "error"
    assert any(b.startswith("docs_drift:") for b in result["blockers"]), (
        f"Expected docs_drift: blocker, got: {result['blockers']}"
    )


def test_release_surface_drift_no_extra_blockers_when_both_clean(
    tmp_path: Path, monkeypatch
) -> None:
    """When both release-text and docs checks are clean, no new blockers appear."""
    root = tmp_path / "root"
    output = tmp_path / "output"
    root.mkdir()
    output.mkdir()
    _build_surface_drift_fixture(root, output, bin_key="omg", action_yml=True)

    monkeypatch.setattr(
        contract_compiler_module,
        "compile_release_surfaces",
        lambda _root, check_only=False: {"status": "ok", "drift": []} if check_only else {"status": "ok", "artifacts": []},
    )
    monkeypatch.setattr(
        contract_compiler_module,
        "check_docs",
        lambda _root: {"status": "ok", "drift": []},
    )

    result = _check_release_surface_drift(root, output)

    assert result["status"] == "ok"
    assert not any(b.startswith("release_text_drift:") for b in result["blockers"])
    assert not any(b.startswith("docs_drift:") for b in result["blockers"])


def test_readiness_fails_when_release_text_drifts(
    tmp_path: Path, monkeypatch
) -> None:
    """build_release_readiness must fail when release-text surfaces drift."""
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    monkeypatch.setattr(
        contract_compiler_module,
        "_check_release_surface_drift",
        lambda _root, _output: {
            "status": "error",
            "blockers": ["release_text_drift: changelog_current content drift in CHANGELOG.md"],
            "checks": {},
        },
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("release_text_drift:" in b for b in readiness["blockers"])


def test_readiness_fails_when_docs_drift(
    tmp_path: Path, monkeypatch
) -> None:
    """build_release_readiness must fail when generated docs drift."""
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)
    _patch_proof_chain_ok(monkeypatch)
    _patch_claim_judge_ok(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=list(CANONICAL_HOSTS),
        channel="public",
    )
    assert compile_result["status"] == "ok"

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
    _write_claim_judge_evidence(tmp_path)
    _write_doctor_success(tmp_path)
    _write_eval_ok(tmp_path)

    monkeypatch.setattr(
        contract_compiler_module,
        "_check_release_surface_drift",
        lambda _root, _output: {
            "status": "error",
            "blockers": ["docs_drift: Missing: support-matrix.json"],
            "checks": {},
        },
    )

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="public")

    assert readiness["status"] == "error"
    assert any("docs_drift:" in b for b in readiness["blockers"])

# ---------------------------------------------------------------------------
# _check_policy_pack_signatures: tampered, untrusted, invalid_signature
# ---------------------------------------------------------------------------


def test_check_policy_pack_signatures_enforcing_tampered(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", "1")
    packs_dir = tmp_path / "registry" / "policy-packs"
    packs_dir.mkdir(parents=True)

    fake_digest = "a" * 64
    for pack_id in ("locked-prod", "fintech", "airgapped"):
        (packs_dir / f"{pack_id}.yaml").write_text(f"id: {pack_id}\nversion: '1.0'\n")
        (packs_dir / f"{pack_id}.lock.json").write_text(
            json.dumps({"canonical_digest": fake_digest})
        )
        (packs_dir / f"{pack_id}.signature.json").write_text(
            json.dumps({
                "artifact_digest": fake_digest,
                "action": "policy-pack-sign",
                "scope": f"policy-pack/{pack_id}",
                "reason": "test",
                "signer_key_id": "test-key",
                "issued_at": "2026-01-01T00:00:00Z",
                "signature": "test-sig",
            })
        )

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "error"
    assert result["enforcing"] is True
    assert len(result["blockers"]) == 3
    assert all("tampered" in b for b in result["blockers"])


def test_check_policy_pack_signatures_enforcing_untrusted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", "1")
    packs_dir = tmp_path / "registry" / "policy-packs"
    packs_dir.mkdir(parents=True)

    digest = "a" * 64
    for pack_id in ("locked-prod", "fintech", "airgapped"):
        (packs_dir / f"{pack_id}.lock.json").write_text(
            json.dumps({"canonical_digest": digest})
        )
        (packs_dir / f"{pack_id}.signature.json").write_text(
            json.dumps({
                "artifact_digest": digest,
                "action": "policy-pack-sign",
                "scope": f"policy-pack/{pack_id}",
                "reason": "test",
                "signer_key_id": "test-key",
                "issued_at": "2026-01-01T00:00:00Z",
                "signature": "test-sig",
            })
        )

    monkeypatch.setattr(
        contract_compiler_module,
        "verify_approval_artifact",
        lambda approval, expected: {"valid": False, "reason": "unknown signer key id"},
    )

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "error"
    assert result["enforcing"] is True
    assert len(result["blockers"]) == 3
    assert all("untrusted" in b for b in result["blockers"])


def test_check_policy_pack_signatures_enforcing_invalid_sig(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_REQUIRE_TRUSTED_POLICY_PACKS", "1")
    packs_dir = tmp_path / "registry" / "policy-packs"
    packs_dir.mkdir(parents=True)

    digest = "a" * 64
    for pack_id in ("locked-prod", "fintech", "airgapped"):
        (packs_dir / f"{pack_id}.lock.json").write_text(
            json.dumps({"canonical_digest": digest})
        )
        (packs_dir / f"{pack_id}.signature.json").write_text(
            json.dumps({
                "artifact_digest": digest,
                "action": "policy-pack-sign",
                "scope": f"policy-pack/{pack_id}",
                "reason": "test",
                "signer_key_id": "test-key",
                "issued_at": "2026-01-01T00:00:00Z",
                "signature": "test-sig",
            })
        )

    monkeypatch.setattr(
        contract_compiler_module,
        "verify_approval_artifact",
        lambda approval, expected: {"valid": False, "reason": "invalid approval signature"},
    )

    result = _check_policy_pack_signatures(tmp_path)

    assert result["status"] == "error"
    assert result["enforcing"] is True
    assert len(result["blockers"]) == 3
    assert all("invalid_signature" in b for b in result["blockers"])
