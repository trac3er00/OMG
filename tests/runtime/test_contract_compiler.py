from __future__ import annotations

import hashlib
import json
from pathlib import Path

from runtime.adoption import CANONICAL_VERSION
from runtime.contract_compiler import build_release_readiness, compile_contract_outputs, validate_contract_registry


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
    }.issubset(bundle_ids)


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

    readiness = build_release_readiness(root_dir=ROOT, output_root=tmp_path, channel="dual")
    assert readiness["status"] == "ok"
    assert readiness["blockers"] == []
