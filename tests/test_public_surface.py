from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from runtime.adoption import CANONICAL_VERSION
from runtime.canonical_taxonomy import CANONICAL_PRESETS

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
    assert "preset" in commands
    assert commands["preset"]["path"] == "commands/OMG:preset.md"


def test_core_plugin_manifest_config_category_includes_preset() -> None:
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text(encoding="utf-8"))
    config_commands = manifest["categories"]["config"]["commands"]

    assert "mode" in config_commands
    assert "preset" in config_commands


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


def test_deep_plan_is_linked_to_plan_council():
    """Assert deep-plan and plan-council are properly connected."""
    # 1. plugin.json maps deep-plan to commands/OMG:deep-plan.md
    manifest = json.loads(
        (ROOT / "plugins" / "advanced" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["commands"]["deep-plan"]["path"] == "commands/OMG:deep-plan.md"

    # 2. The command file itself is a full 5-track planning command
    cmd_text = (ROOT / "plugins" / "advanced" / "commands" / "OMG:deep-plan.md").read_text(
        encoding="utf-8"
    )
    assert "deep-plan" in cmd_text.lower()
    assert "5-track" in cmd_text.lower() or "5 track" in cmd_text.lower()
    # plan-council evidence artifact is referenced
    assert "plan-council" in cmd_text

    # 3. plan-council bundle references the plugin-relative command path
    bundle = yaml.safe_load(
        (ROOT / "registry" / "bundles" / "plan-council.yaml").read_text(encoding="utf-8")
    )
    refs = bundle["assets"]["references"]
    assert any(
        "plugins/advanced/commands/OMG:deep-plan.md" in str(r) for r in refs
    ), f"plan-council bundle references do not include plugin-relative deep-plan path: {refs}"

    # 4. README.md advertises /OMG:deep-plan
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "/OMG:deep-plan" in readme

    # 5. plugins/README.md mentions /OMG:deep-plan
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    assert "/OMG:deep-plan" in plugins_readme


def test_plugins_readme_leads_with_launcher_first_install_story():
    plugins_readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    assert "npx omg env doctor" in plugins_readme
    assert "npx omg install --plan" in plugins_readme
    assert plugins_readme.index("npx omg env doctor") < plugins_readme.index("/OMG:setup")


def test_scripts_omg_docstring_has_no_stale_version_literal():
    cli_text = (ROOT / "scripts" / "omg.py").read_text(encoding="utf-8")
    assert "2.0.8 CLI entrypoint" not in cli_text


def test_package_includes_operator_docs_in_published_artifact():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    files = set(pkg["files"])
    assert "docs/install/" in files
    assert "docs/proof.md" in files
    assert "QUICK-REFERENCE.md" in files
    assert "INSTALL-VERIFICATION-INDEX.md" in files


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


def test_core_plugin_command_paths_resolve_relative_to_plugin_root():
    """Verify all command paths in core plugin resolve relative to repo root (core commands live at ROOT/commands/)"""
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text(encoding="utf-8"))

    for cmd_name, cmd_config in manifest["commands"].items():
        path = cmd_config["path"]
        resolved = ROOT / path
        assert resolved.exists(), f"Command '{cmd_name}' path '{path}' does not resolve to {resolved}"


def test_omg_deep_plan_root_command_exists():
    """Assert commands/OMG:deep-plan.md exists as a full 5-track strategic planning command."""
    cmd_path = ROOT / "commands" / "OMG:deep-plan.md"
    assert cmd_path.exists(), f"Command file {cmd_path} does not exist"

    content = cmd_path.read_text(encoding="utf-8")
    assert "5-track" in content.lower() or "5 track" in content.lower(), \
        "deep-plan must reference 5-track architecture"
    assert "architect" in content.lower(), \
        "deep-plan must include architect track"
    assert "/OMG:deep-plan" in content or "deep-plan" in content.lower(), \
        "Command must reference deep-plan"


def test_no_stale_presets_in_public_docs() -> None:
    setup_doc = (ROOT / "commands" / "OMG:setup.md").read_text(encoding="utf-8")

    mentioned_presets: set[str] = set()

    hint_match = re.search(r"--preset\s+([^\]]+)", setup_doc)
    if hint_match:
        for token in hint_match.group(1).split("|"):
            mentioned_presets.add(token.strip())

    in_preset_step = False
    for raw_line in setup_doc.splitlines():
        line = raw_line.strip()
        if line.lower() == "step 4: choose preset":
            in_preset_step = True
            continue
        if in_preset_step and line.startswith("Step "):
            break
        if in_preset_step and line.startswith("- "):
            mentioned_presets.add(line[2:].strip().split(" ", 1)[0])

    stale = sorted(p for p in mentioned_presets if p and p not in CANONICAL_PRESETS)
    assert stale == [], f"Stale presets in commands/OMG:setup.md: {stale}"


def test_no_hardcoded_version_drift() -> None:
    version_pattern = re.compile(r"\bv?\d+\.\d+\.\d+\b")
    template_pattern = re.compile(r"VERSION", re.IGNORECASE)
    omg_context_pattern = re.compile(r"\bomg\b|\bcanonical\b", re.IGNORECASE)

    targets = [ROOT / "README.md"]
    targets.extend(sorted((ROOT / "docs").rglob("*.md")))
    targets.extend(sorted((ROOT / "commands").rglob("*.md")))

    drift: list[str] = []
    for path in targets:
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not version_pattern.search(raw_line):
                continue
            if template_pattern.search(raw_line):
                continue
            if not omg_context_pattern.search(raw_line):
                continue

            for match in version_pattern.finditer(raw_line):
                candidate = match.group(0).lstrip("v")
                if candidate != CANONICAL_VERSION:
                    rel = path.relative_to(ROOT)
                    drift.append(f"{rel}:{lineno}:{match.group(0)}")

    assert drift == [], "Hard-coded OMG version drift found: " + ", ".join(drift)


# ---------------------------------------------------------------------------
# Error / edge case / regression tests
# ---------------------------------------------------------------------------


def test_plugin_manifests_are_valid_json() -> None:
    """Malformed plugin.json breaks all command resolution."""
    for manifest_path in ROOT.rglob("plugin.json"):
        raw = manifest_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Invalid JSON in {manifest_path}: {exc}") from exc
        assert isinstance(data, dict), f"{manifest_path} top-level must be a dict"


def test_core_plugin_commands_dict_is_not_empty() -> None:
    """An empty commands dict means no skills will resolve at all."""
    manifest = json.loads((ROOT / "plugins" / "core" / "plugin.json").read_text(encoding="utf-8"))
    assert len(manifest["commands"]) > 0, "Core plugin must expose at least one command"


def test_command_files_are_not_zero_byte() -> None:
    """Zero-byte command files silently break skill resolution."""
    cmd_dir = ROOT / "commands"
    for md in sorted(cmd_dir.glob("OMG:*.md")):
        if md.is_symlink():
            continue
        size = md.stat().st_size
        assert size > 0, f"{md.name} is zero bytes"


def test_registry_bundles_are_valid_yaml() -> None:
    """Malformed bundle YAML breaks proof-gate and plan-council."""
    bundle_dir = ROOT / "registry" / "bundles"
    if not bundle_dir.exists():
        return
    for bundle_path in sorted(bundle_dir.glob("*.yaml")):
        raw = bundle_path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise AssertionError(f"Invalid YAML in {bundle_path}: {exc}") from exc
        assert isinstance(data, dict), f"{bundle_path} must be a dict"


def test_package_json_version_matches_canonical() -> None:
    """package.json version must match the runtime canonical version."""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == CANONICAL_VERSION, (
        f"package.json version {pkg['version']} != canonical {CANONICAL_VERSION}"
    )


def test_readme_does_not_reference_deleted_workflows() -> None:
    """Regression: stale badge/CI references to workflows that were removed."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    deleted = ["omg-compat-gate.yml", "omg-release-readiness.yml", "evidence-gate.yml"]
    for wf in deleted:
        assert wf not in readme, f"README.md still references deleted workflow {wf}"


def test_schema_file_is_valid_json() -> None:
    """The capability schema must parse without errors."""
    schema_path = ROOT / "registry" / "omg-capability.schema.json"
    if not schema_path.exists():
        return
    raw = schema_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "properties" in data, "Schema must have properties"
