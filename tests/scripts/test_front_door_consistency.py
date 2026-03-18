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
        """README 'Then run:' section should use launcher syntax as primary."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        then_run_idx = readme.find("Then run:")
        assert then_run_idx >= 0, "README must have a 'Then run:' section"
        block_start = readme.find("```", then_run_idx)
        block_end = readme.find("```", block_start + 3) if block_start >= 0 else -1
        if block_start >= 0 and block_end >= 0:
            run_block = readme[block_start:block_end]
            assert "npx omg " in run_block, (
                "Primary run block should use the launcher-first npx syntax"
            )
            assert "omg ship <goal>" not in run_block, (
                "Primary run block should not advertise unsupported positional ship syntax"
            )

    def test_claude_code_run_section_uses_launcher(self) -> None:
        """claude-code.md Run section should use launcher syntax as primary."""
        path = REPO_ROOT / "docs" / "install" / "claude-code.md"
        if not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        run_idx = content.find("## Run")
        assert run_idx >= 0, "claude-code.md must have a Run section"
        next_section = content.find("\n## ", run_idx + 1)
        section = content[run_idx : next_section if next_section > 0 else len(content)]
        block_start = section.find("```")
        block_end = section.find("```", block_start + 3) if block_start >= 0 else -1
        if block_start >= 0 and block_end >= 0:
            run_block = section[block_start:block_end]
            assert "npx omg " in run_block, (
                "claude-code.md primary run block should use the launcher-first npx syntax"
            )
            assert "omg ship <goal>" not in run_block, (
                "claude-code.md primary run block should not advertise unsupported positional ship syntax"
            )

    def test_promoted_commands_use_real_cli_shapes(self) -> None:
        """Generated promoted commands must use the real canonical CLI syntax."""
        promoted = get_promoted_public_commands()
        assert "omg explain run --run-id <id>" in promoted
        assert "omg explain run <id>" not in promoted
        assert "omg doctor" in promoted
