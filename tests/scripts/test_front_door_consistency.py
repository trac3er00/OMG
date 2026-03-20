"""Tests that the project presents a consistent primary front door.

Prevents the recurring issue where authored docs use /OMG:* slash commands
as primary entry points while generated sections use omg launcher syntax.
The launcher is the universal primary; slash commands are Claude-specific compatibility.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from runtime.release_surface_registry import get_promoted_public_commands


class TestFrontDoorConsistency:
    """Launcher syntax must be primary everywhere."""

    def test_native_adoption_public_onboarding_is_launcher_first(self) -> None:
        """Native adoption guide must describe launcher-first onboarding."""
        path = REPO_ROOT / "docs" / "migration" / "native-adoption.md"
        content = path.read_text(encoding="utf-8")
        assert "Public onboarding is launcher-first:" in content
        assert "npx omg env doctor" in content
        assert "npx omg install --plan" in content
        assert "npx omg install --apply" in content
        assert "Legacy Claude aliases" in content

    def test_readme_command_surface_demotes_legacy_aliases(self) -> None:
        """README should subordinate slash-command aliases to the launcher list."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        cmd_idx = readme.find("## Command Surface")
        assert cmd_idx >= 0, "README must have a Command Surface section"
        next_section = readme.find("\n## ", cmd_idx + 1)
        section = readme[cmd_idx : next_section if next_section > 0 else len(readme)]
        assert "> **Legacy/advanced aliases**:" in section
        legacy_pos = section.find("> **Legacy/advanced aliases**:")
        launcher_pos = section.find("- `npx omg env doctor`")
        assert legacy_pos >= 0, "Section must contain legacy aliases marker"
        assert launcher_pos >= 0, "Section must contain launcher command"
        assert legacy_pos > launcher_pos

    def test_readme_quickstart_has_single_authoritative_launcher_flow(self) -> None:
        """README quickstart should not append older generated launcher blocks."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "<!-- OMG:GENERATED:quickstart -->" not in readme
        assert "<!-- OMG:GENERATED:command-surface -->" not in readme
        assert "<!-- OMG:GENERATED:proof -->" not in readme
        assert "Canonical launcher-first flow:" not in readme
        assert "npm install @trac3er/oh-my-god" not in readme

    def test_host_guides_demote_legacy_clone_paths(self) -> None:
        """Manual clone paths should be hidden behind legacy/advanced disclosure."""
        for guide in ("codex.md", "gemini.md", "kimi.md", "opencode.md"):
            path = REPO_ROOT / "docs" / "install" / guide
            content = path.read_text(encoding="utf-8")
            assert "<details><summary>Restricted environments / manual setup</summary>" in content, guide
            assert "## Manual Path" not in content, guide

    def test_host_guides_have_single_fast_path_section(self) -> None:
        """Launcher-first install guides should not keep duplicate fast-path blocks."""
        for guide in ("claude-code.md", "codex.md", "opencode.md", "gemini.md", "kimi.md"):
            path = REPO_ROOT / "docs" / "install" / guide
            content = path.read_text(encoding="utf-8")
            assert content.count("## Fast Path") == 1, guide

    def test_claude_code_browser_legacy_script_is_disclosed(self) -> None:
        """Legacy setup-script browser path should be visually subordinate in Claude docs."""
        path = REPO_ROOT / "docs" / "install" / "claude-code.md"
        content = path.read_text(encoding="utf-8")
        assert "<details><summary>Restricted environments: legacy browser setup</summary>" in content
        assert "./OMG-setup.sh install --enable-browser" in content

    def test_install_verification_index_uses_npx_commands(self) -> None:
        """Install verification index should not assume a globally linked omg binary."""
        path = REPO_ROOT / "INSTALL-VERIFICATION-INDEX.md"
        content = path.read_text(encoding="utf-8")
        assert "npx omg doctor" in content
        assert "npx omg validate" in content
        assert "npx omg install --plan" in content
        assert "`omg doctor`" not in content

    def test_readme_why_omg_claude_front_door_uses_launcher(self) -> None:
        """README Why OMG section must describe Claude with launcher-first wording."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        why_idx = readme.find("## Why OMG")
        assert why_idx >= 0, "README must have a Why OMG section"
        next_section = readme.find("\n## ", why_idx + 1)
        section = readme[why_idx : next_section if next_section > 0 else len(readme)]
        line = next(
            (raw for raw in section.splitlines() if "Claude front door:" in raw),
            "",
        )
        assert line, "Why OMG section must mention the Claude front door"
        assert "omg " in line, "Claude front door must use launcher syntax"
        if "/OMG:" in line:
            assert line.index("omg ") < line.index("/OMG:"), (
                "Claude front door must present launcher syntax before slash-command compatibility aliases"
            )

    def test_readme_command_surface_leads_with_launcher(self) -> None:
        """README Command Surface section must mention launcher commands before slash commands."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        cmd_idx = readme.find("## Command Surface")
        assert cmd_idx >= 0, "README must have a Command Surface section"
        next_section = readme.find("\n## ", cmd_idx + 1)
        section = readme[cmd_idx : next_section if next_section > 0 else len(readme)]
        launcher_pos = section.find("omg ")
        slash_pos = section.find("/OMG:")
        assert launcher_pos >= 0, "Command Surface must mention launcher commands"
        if slash_pos >= 0:
            assert launcher_pos < slash_pos, (
                "Command Surface must mention launcher commands before slash commands"
            )

    def test_readme_quickstart_run_uses_launcher(self) -> None:
        """README quickstart should use launcher syntax as the only primary flow."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        quickstart_idx = readme.find("## Quickstart")
        assert quickstart_idx >= 0, "README must have a Quickstart section"
        block_start = readme.find("```", quickstart_idx)
        block_end = readme.find("```", block_start + 3) if block_start >= 0 else -1
        if block_start >= 0 and block_end >= 0:
            run_block = readme[block_start:block_end]
            assert "npx omg " in run_block, (
                "Primary run block should use the launcher-first npx syntax"
            )
            assert "npx omg ship" in run_block
            assert "# confirm preview output before applying" in run_block

    def test_claude_code_run_section_uses_launcher(self) -> None:
        """claude-code.md fast path should use launcher syntax as primary."""
        path = REPO_ROOT / "docs" / "install" / "claude-code.md"
        if not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        run_idx = content.find("## Fast Path")
        assert run_idx >= 0, "claude-code.md must have a Fast Path section"
        next_section = content.find("\n## ", run_idx + 1)
        section = content[run_idx : next_section if next_section > 0 else len(content)]
        block_start = section.find("```")
        block_end = section.find("```", block_start + 3) if block_start >= 0 else -1
        if block_start >= 0 and block_end >= 0:
            run_block = section[block_start:block_end]
            assert "npx omg " in run_block, (
                "claude-code.md primary fast path should use the launcher-first npx syntax"
            )
            assert "npx omg install --apply" in run_block

    def test_promoted_commands_use_real_cli_shapes(self) -> None:
        """Generated promoted commands must use the real canonical CLI syntax."""
        promoted = get_promoted_public_commands()
        assert "omg explain run --run-id <id>" in promoted
        assert "omg explain run <id>" not in promoted
        assert "omg doctor" in promoted
