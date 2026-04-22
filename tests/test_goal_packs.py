"""Integration tests for Goal Packs scaffold execution.

Tests all 6 goal packs: saas, landing, discord-bot, cli-tool, api-server, internal-tool.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from runtime.goal_packs import execute_goal_pack, list_goal_packs


# Expected file counts per pack (based on verified scaffold directories)
PACK_EXPECTED_FILES = {
    "saas": 4,
    "landing": 2,
    "discord-bot": 3,
    "cli-tool": 3,
    "api-server": 3,
    "internal-tool": 3,
}

# Patterns indicating stub/placeholder content that shouldn't exist in production scaffolds
STUB_PATTERNS = [
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"not implemented",
    r"implement me",
    r"fill in",
    r"your code here",
]

STUB_REGEX = re.compile("|".join(STUB_PATTERNS), re.IGNORECASE)


class TestListGoalPacks:
    """Tests for list_goal_packs() function."""

    def test_list_goal_packs_returns_six(self) -> None:
        """Verify exactly 6 goal packs are available."""
        packs = list_goal_packs()
        assert len(packs) == 6, f"Expected 6 packs, got {len(packs)}: {packs}"

    def test_list_goal_packs_contains_all_expected(self) -> None:
        """Verify all expected pack names are present."""
        packs = list_goal_packs()
        expected = {"saas", "landing", "discord-bot", "cli-tool", "api-server", "internal-tool"}
        assert set(packs) == expected, f"Missing packs: {expected - set(packs)}"

    def test_list_goal_packs_returns_sorted(self) -> None:
        """Verify packs are returned in sorted order."""
        packs = list_goal_packs()
        assert packs == sorted(packs), "Packs should be sorted alphabetically"


class TestSaasGoalPack:
    """Tests for the saas goal pack."""

    def test_saas_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify saas pack creates expected files."""
        result = execute_goal_pack("saas", str(tmp_path), {"project_name": "test-saas"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "saas"
        assert len(result["files"]) == PACK_EXPECTED_FILES["saas"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_saas_no_stubs(self, tmp_path: Path) -> None:
        """Verify saas pack has no TODO/placeholder content."""
        result = execute_goal_pack("saas", str(tmp_path), {"project_name": "test-saas"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


class TestLandingGoalPack:
    """Tests for the landing goal pack."""

    def test_landing_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify landing pack creates expected files."""
        result = execute_goal_pack("landing", str(tmp_path), {"project_name": "test-landing"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "landing"
        assert len(result["files"]) == PACK_EXPECTED_FILES["landing"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_landing_no_stubs(self, tmp_path: Path) -> None:
        """Verify landing pack has no TODO/placeholder content."""
        result = execute_goal_pack("landing", str(tmp_path), {"project_name": "test-landing"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


class TestDiscordBotGoalPack:
    """Tests for the discord-bot goal pack."""

    def test_discord_bot_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify discord-bot pack creates expected files."""
        result = execute_goal_pack("discord-bot", str(tmp_path), {"project_name": "test-bot"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "discord-bot"
        assert len(result["files"]) == PACK_EXPECTED_FILES["discord-bot"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_discord_bot_no_stubs(self, tmp_path: Path) -> None:
        """Verify discord-bot pack has no TODO/placeholder content."""
        result = execute_goal_pack("discord-bot", str(tmp_path), {"project_name": "test-bot"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


class TestCliToolGoalPack:
    """Tests for the cli-tool goal pack."""

    def test_cli_tool_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify cli-tool pack creates expected files."""
        result = execute_goal_pack("cli-tool", str(tmp_path), {"project_name": "test-cli"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "cli-tool"
        assert len(result["files"]) == PACK_EXPECTED_FILES["cli-tool"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_cli_tool_no_stubs(self, tmp_path: Path) -> None:
        """Verify cli-tool pack has no TODO/placeholder content."""
        result = execute_goal_pack("cli-tool", str(tmp_path), {"project_name": "test-cli"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


class TestApiServerGoalPack:
    """Tests for the api-server goal pack."""

    def test_api_server_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify api-server pack creates expected files."""
        result = execute_goal_pack("api-server", str(tmp_path), {"project_name": "test-api"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "api-server"
        assert len(result["files"]) == PACK_EXPECTED_FILES["api-server"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_api_server_no_stubs(self, tmp_path: Path) -> None:
        """Verify api-server pack has no TODO/placeholder content."""
        result = execute_goal_pack("api-server", str(tmp_path), {"project_name": "test-api"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


class TestInternalToolGoalPack:
    """Tests for the internal-tool goal pack."""

    def test_internal_tool_scaffold_creates_files(self, tmp_path: Path) -> None:
        """Verify internal-tool pack creates expected files."""
        result = execute_goal_pack("internal-tool", str(tmp_path), {"project_name": "test-internal"})
        
        assert result["success"] is True, f"Scaffold failed: {result.get('error')}"
        assert result["pack"] == "internal-tool"
        assert len(result["files"]) == PACK_EXPECTED_FILES["internal-tool"]
        
        for file_path in result["files"]:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"File not created: {file_path}"

    def test_internal_tool_no_stubs(self, tmp_path: Path) -> None:
        """Verify internal-tool pack has no TODO/placeholder content."""
        result = execute_goal_pack("internal-tool", str(tmp_path), {"project_name": "test-internal"})
        assert result["success"] is True
        
        _assert_no_stubs_in_files(tmp_path, result["files"])


def _assert_no_stubs_in_files(base_path: Path, files: list[str]) -> None:
    """Assert that no files contain stub/placeholder patterns."""
    stub_found: list[tuple[str, str, str]] = []
    
    for file_path in files:
        full_path = base_path / file_path
        if not full_path.exists():
            continue
            
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
            
        for line_num, line in enumerate(content.splitlines(), start=1):
            match = STUB_REGEX.search(line)
            if match:
                stub_found.append((file_path, str(line_num), match.group(0)))
    
    if stub_found:
        details = "\n".join(f"  {f}:{ln}: found '{m}'" for f, ln, m in stub_found)
        pytest.fail(f"Stub patterns found in generated files:\n{details}")
