from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import pytest
import yaml
from runtime.adoption import CANONICAL_VERSION
from runtime.evidence_requirements import requirements_for_profile
from runtime import contract_compiler as contract_compiler_module
from runtime.contract_compiler import (
    DEFAULT_REQUIRED_BUNDLES,
    REQUIRED_ADVANCED_PLUGIN_ARTIFACTS,
    REQUIRED_CLAUDE_HOOK_EVENTS,
    REQUIRED_CLAUDE_SUBAGENT_NAMES,
    REQUIRED_CODEX_AGENTS_SECTIONS,
    REQUIRED_CODEX_OUTPUTS,
    build_release_readiness,
    compile_contract_outputs,
    validate_contract_registry,
    _validate_compiled_claude_output,
    _validate_compiled_codex_output,
)

# The four truth/council bundles that must always be present in canonical surfaces.
TRUTH_COUNCIL_BUNDLES = ("plan-council", "claim-judge", "test-intent-lock", "proof-gate")


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


def test_release_readiness_accepts_schema_v2_evidence_fixture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RELEASE_READY_PROVIDERS", "claude,codex")
    _patch_fast_release_checks(monkeypatch)

    compile_result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
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
    control_plane["hosts"] = ["claude", "codex", "gemini", "kimi"]
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
    control_plane["hosts"] = ["claude", "codex", "gemini"]
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


def test_compile_contract_outputs_writes_claude_codex_and_dist_artifacts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["claude", "codex"],
        channel="enterprise",
    )

    assert result["schema"] == "OmgContractCompileResult"
    assert result["status"] == "ok"

    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    skill_path = tmp_path / ".agents" / "skills" / "omg" / "control-plane" / "SKILL.md"
    skill_meta_path = tmp_path / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml"
    dist_manifest = tmp_path / "dist" / "enterprise" / "manifest.json"

    assert plugin_path.exists()
    assert skill_path.exists()
    assert skill_meta_path.exists()
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
    assert "bundle/.agents/skills/omg/plan-council/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/security-check/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/tracebank/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/remote-supervisor/SKILL.md" in output_paths


def test_compile_contract_outputs_writes_gemini_artifacts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["gemini"],
        channel="public",
    )

    assert result["status"] == "ok"
    gemini_path = tmp_path / ".gemini" / "settings.json"
    assert gemini_path.exists()

    gemini_payload = json.loads(gemini_path.read_text(encoding="utf-8"))
    assert gemini_payload["mcpServers"]["omg-control"]["command"] == "python3"
    assert gemini_payload["mcpServers"]["omg-control"]["args"] == ["-m", "runtime.omg_mcp_server"]


def test_compile_contract_outputs_writes_kimi_artifacts(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["kimi"],
        channel="public",
    )

    assert result["status"] == "ok"
    kimi_path = tmp_path / ".kimi" / "mcp.json"
    assert kimi_path.exists()

    kimi_payload = json.loads(kimi_path.read_text(encoding="utf-8"))
    assert kimi_payload["mcpServers"]["omg-control"]["command"] == "python3"
    assert kimi_payload["mcpServers"]["omg-control"]["args"] == ["-m", "runtime.omg_mcp_server"]


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
        hosts=["claude", "codex", "gemini"],
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

    for channel in ("public", "enterprise"):
        dist_root = tmp_path / "dist" / channel
        manifest = json.loads((dist_root / "manifest.json").read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            artifact_path = dist_root / artifact["path"]
            assert artifact_path.exists()
            actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            assert actual_sha == artifact["sha256"]

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
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
    assert "security-reviewer" in names
    assert "release-manager" in names

    for sa in subagents:
        assert sa.get("bypassPermissions") is not True, f"{sa['name']} has bypassPermissions"

    reviewer = next(sa for sa in subagents if sa["name"] == "security-reviewer")
    assert "Read" in reviewer["tools"]
    assert "Write" not in reviewer["tools"]

    manager = next(sa for sa in subagents if sa["name"] == "release-manager")
    assert "Write" in manager["tools"]
    assert "protectedPaths" in manager

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

    for req in REQUIRED_ADVANCED_PLUGIN_ARTIFACTS:
        assert req in manifest_paths, f"Missing required advanced artifact: {req}"


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
        cmd_rel_path = cmd_info.get("path", "")
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

    _write_evidence(tmp_path, include_lineage=True, include_attribution=True)
    _write_execution_primitives(tmp_path)
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
        "[project]\nname = 'oh-my-god'\nversion = '2.1.1'\n",
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
