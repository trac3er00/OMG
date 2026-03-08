from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_readme_and_docs_promote_security_check_not_security_review():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    proof = (ROOT / "docs" / "proof.md").read_text(encoding="utf-8")

    assert "/OMG:security-check" in readme
    assert "/OMG:security-review" not in readme
    assert "/OMG:security-review" not in plugins_readme
    assert "/OMG:security-review" not in proof


def test_core_plugin_manifest_includes_new_canonical_surfaces():
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text(encoding="utf-8"))
    commands = manifest["commands"]

    assert "security-check" in commands
    assert "api-twin" in commands
    assert "preflight" in commands
    assert "browser" in commands


def test_advanced_plugin_manifest_no_longer_markets_security_review():
    manifest = json.loads((ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8"))
    assert "security-review" not in manifest["commands"]


def test_advanced_plugin_command_paths_resolve_relative_to_plugin_root():
    """Verify all command paths in advanced plugin resolve relative to plugins/advanced/"""
    manifest = json.loads((ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8"))
    plugin_root = ROOT / "plugins" / "advanced"
    
    for cmd_name, cmd_config in manifest["commands"].items():
        path = cmd_config["path"]
        resolved = plugin_root / path
        assert resolved.exists(), f"Command '{cmd_name}' path '{path}' does not resolve to {resolved}"


def test_readme_promotes_narrowed_mcp_and_truth_bundles():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "narrowed defaults" in readme
    assert "claim-judge" in readme
    assert "test-intent-lock" in readme
    assert "proof-gate" in readme
    assert "plan-council" in readme
    assert "/OMG:deep-plan" in readme


def test_readme_and_plugin_docs_promote_browser_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    proof = (ROOT / "docs" / "proof.md").read_text(encoding="utf-8")

    assert "/OMG:browser" in readme
    assert "/OMG:playwright" in readme
    assert "/OMG:browser" in plugins_readme
    assert "/OMG:browser" in proof


def test_deep_plan_is_compatibility_path_to_plan_council():
    """Assert the deep-plan/plan-council compatibility relationship end-to-end."""
    # 1. plugin.json maps deep-plan to commands/OMG:deep-plan.md
    manifest = json.loads(
        (ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["commands"]["deep-plan"]["path"] == "commands/OMG:deep-plan.md"

    # 2. The command file itself mentions deep-plan and declares compatibility
    cmd_text = (ROOT / "plugins" / "advanced" / "commands" / "OMG:deep-plan.md").read_text(
        encoding="utf-8"
    )
    assert "deep-plan" in cmd_text.lower()
    assert "compatibility" in cmd_text.lower()
    assert "plan-council" in cmd_text

    # 3. plan-council bundle references the plugin-relative command path
    bundle = yaml.safe_load(
        (ROOT / "registry" / "bundles" / "plan-council.yaml").read_text(encoding="utf-8")
    )
    refs = bundle["assets"]["references"]
    assert any(
        "plugins/advanced/commands/OMG:deep-plan.md" in str(r) for r in refs
    ), f"plan-council bundle references do not include plugin-relative deep-plan path: {refs}"

    # 4. README.md advertises /OMG:deep-plan as compatibility path to plan-council
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "/OMG:deep-plan" in readme
    assert "compatibility path to `plan-council`" in readme

    # 5. plugins/README.md uses the same framing
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    assert "/OMG:deep-plan" in plugins_readme
    assert "compatibility path to `plan-council`" in plugins_readme


def test_proof_docs_include_truth_bundle_artifacts():
    proof = (ROOT / "docs" / "proof.md").read_text(encoding="utf-8")
    assert "claim-judge" in proof
    assert "test-intent-lock" in proof
    assert "proof-gate" in proof
    assert "browser-*.png" in proof
    assert "narrowed stdio OMG control" in proof


def test_contract_doc_canonical_hosts_include_gemini_and_kimi() -> None:
    contract_doc = (ROOT / "OMG_COMPAT_CONTRACT.md").read_text(encoding="utf-8")
    parts = contract_doc.split("---", 2)
    assert len(parts) == 3
    front_matter = yaml.safe_load(parts[1])

    assert front_matter["canonical_hosts"] == ["claude", "codex", "gemini", "kimi"]


def test_schema_hosts_enum_includes_all_canonical_hosts() -> None:
    schema = json.loads((ROOT / "registry" / "omg-capability.schema.json").read_text(encoding="utf-8"))
    hosts = schema.get("properties", {}).get("hosts", {}).get("items", {}).get("enum", [])
    assert set(hosts) == {"claude", "codex", "gemini", "kimi"}
