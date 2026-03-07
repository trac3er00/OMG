from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import yaml
from runtime.adoption import CANONICAL_VERSION
from runtime import contract_compiler as contract_compiler_module
from runtime.contract_compiler import (
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


ROOT = Path(__file__).resolve().parents[2]


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
) -> None:
    payload: dict[str, object] = {
        "schema": "EvidencePack",
        "run_id": "run-1",
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
    }
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


def test_validate_contract_registry_reports_expected_bundles() -> None:
    result = validate_contract_registry(ROOT)

    assert result["schema"] == "OmgContractValidationResult"
    assert result["status"] == "ok"
    assert result["contract"]["version"] == CANONICAL_VERSION
    bundle_ids = {bundle["id"] for bundle in result["bundles"]}
    assert {
        "control-plane",
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
    }.issubset(bundle_ids)


def test_validate_contract_registry_accepts_valid_policy_model() -> None:
    result = validate_contract_registry(ROOT)

    assert result["status"] == "ok"
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
    assert "bundle/.agents/skills/omg/security-check/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/tracebank/SKILL.md" in output_paths
    assert "bundle/.agents/skills/omg/remote-supervisor/SKILL.md" in output_paths


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
