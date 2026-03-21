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


def test_omg_deep_plan_root_stub_exists():
    """Assert commands/OMG:deep-plan.md exists as a root slash-command stub coupled to plan-council."""
    stub_path = ROOT / "commands" / "OMG:deep-plan.md"
    assert stub_path.exists(), f"Root stub {stub_path} does not exist"

    content = stub_path.read_text(encoding="utf-8")
    assert "plan-council" in content, "Root stub must reference plan-council"
    assert "compatibility" in content.lower() or "alias" in content.lower(), \
        "Root stub must declare compatibility or alias relationship"
    assert "/OMG:deep-plan" in content, "Root stub must reference /OMG:deep-plan"


def test_no_stale_presets_in_public_docs() -> None:
    # Presets are now documented in OMG:init.md (setup was merged into init)
    init_doc = (ROOT / "commands" / "OMG:init.md").read_text(encoding="utf-8")

    mentioned_presets: set[str] = set()

    hint_match = re.search(r"--preset\s+([^\]]+)", init_doc)
    if hint_match:
        for token in hint_match.group(1).split("|"):
            mentioned_presets.add(token.strip())

    in_preset_step = False
    for raw_line in init_doc.splitlines():
        line = raw_line.strip()
        if line.lower() == "step 4: choose preset":
            in_preset_step = True
            continue
        if in_preset_step and line.startswith("Step "):
            break
        if in_preset_step and line.startswith("- "):
            mentioned_presets.add(line[2:].strip().split(" ", 1)[0])

    stale = sorted(p for p in mentioned_presets if p and p not in CANONICAL_PRESETS)
    assert stale == [], f"Stale presets in commands/OMG:init.md: {stale}"


# --- Command Consolidation Tests ---
# Verify deprecated commands redirect and new consolidated commands are well-formed.

_DEPRECATED_COMMANDS = {
    "OMG:doctor.md": "/OMG:validate",
    "OMG:health-check.md": "/OMG:validate",
    "OMG:diagnose-plugins.md": "/OMG:validate",
    "OMG:setup.md": "/OMG:init",
    "OMG:session-branch.md": "/OMG:session",
    "OMG:session-fork.md": "/OMG:session",
    "OMG:session-merge.md": "/OMG:session",
    "OMG:ralph-start.md": "/OMG:ralph",
    "OMG:ralph-stop.md": "/OMG:ralph",
    "OMG:ccg.md": "/OMG:crazy",
    "OMG:teams.md": "/OMG:crazy",
    "OMG:cost.md": "/OMG:stats",
}

_REMOVED_COMMANDS = {"OMG:playwright.md", "OMG:compat.md", "OMG:theme.md"}

_CONSOLIDATED_COMMANDS = {
    "OMG:validate.md": ["doctor", "health", "plugins"],
    "OMG:session.md": ["branch", "fork", "merge"],
    "OMG:ralph.md": ["start", "stop", "status"],
    "OMG:crazy.md": ["ccg", "team"],
    "OMG:stats.md": ["cost"],
}


def test_deprecated_commands_have_redirect_message() -> None:
    """Every deprecated command must mention DEPRECATED and point to canonical replacement."""
    for filename, canonical in _DEPRECATED_COMMANDS.items():
        path = ROOT / "commands" / filename
        assert path.exists(), f"Deprecated stub missing: {filename}"
        content = path.read_text(encoding="utf-8")
        assert "DEPRECATED" in content, f"{filename} missing DEPRECATED marker"
        assert canonical in content, f"{filename} missing redirect to {canonical}"


def test_removed_commands_have_removed_message() -> None:
    """Every removed command must mention REMOVED."""
    for filename in _REMOVED_COMMANDS:
        path = ROOT / "commands" / filename
        assert path.exists(), f"Removed stub missing: {filename}"
        content = path.read_text(encoding="utf-8")
        assert "REMOVED" in content, f"{filename} missing REMOVED marker"


def test_deprecated_commands_have_minimal_tools() -> None:
    """Deprecated commands should not grant broad tool access — only Read."""
    for filename in _DEPRECATED_COMMANDS:
        path = ROOT / "commands" / filename
        content = path.read_text(encoding="utf-8")
        # Extract allowed-tools from frontmatter
        for line in content.splitlines():
            if line.startswith("allowed-tools:"):
                tools = line.split(":", 1)[1].strip()
                assert tools == "Read", (
                    f"{filename} grants tools beyond Read: {tools}"
                )
                break


def test_consolidated_commands_exist_and_have_subcommands() -> None:
    """Each consolidated command file must exist and document its sub-commands."""
    for filename, subcommands in _CONSOLIDATED_COMMANDS.items():
        path = ROOT / "commands" / filename
        assert path.exists(), f"Consolidated command missing: {filename}"
        content = path.read_text(encoding="utf-8").lower()
        for sub in subcommands:
            assert sub in content, (
                f"{filename} missing subcommand documentation for '{sub}'"
            )


def test_consolidated_commands_have_frontmatter() -> None:
    """Consolidated commands must have valid YAML frontmatter with description and allowed-tools."""
    for filename in _CONSOLIDATED_COMMANDS:
        path = ROOT / "commands" / filename
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{filename} missing frontmatter"
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{filename} has malformed frontmatter"
        fm = yaml.safe_load(parts[1])
        assert "description" in fm, f"{filename} frontmatter missing description"
        assert "allowed-tools" in fm, f"{filename} frontmatter missing allowed-tools"
        assert "[DEPRECATED]" not in fm["description"], (
            f"{filename} is consolidated but has DEPRECATED in description"
        )


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
