from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import yaml
from runtime.adoption import CANONICAL_VERSION
from runtime.contract_compiler import (
    REQUIRED_CLAUDE_HOOK_EVENTS,
    REQUIRED_CLAUDE_SUBAGENT_NAMES,
    build_release_readiness,
    compile_contract_outputs,
    validate_contract_registry,
    _validate_compiled_claude_output,
)


ROOT = Path(__file__).resolve().parents[2]


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
