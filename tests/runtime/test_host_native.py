"""Host-native feel: instant mode references and config validity across 5 providers."""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestHostNativeFeel:
    def test_claude_plugin_json_contains_instant_reference(self) -> None:
        """Claude plugin.json references instant mode."""
        plugin_path = ROOT / ".claude-plugin" / "plugin.json"
        assert plugin_path.exists(), f"Missing {plugin_path}"
        data = json.loads(plugin_path.read_text())
        raw = json.dumps(data).lower()
        assert "instant" in raw, "plugin.json must contain an 'instant' reference"

    def test_codex_agents_fragment_mentions_instant_mode(self) -> None:
        """Codex AGENTS.fragment.md mentions instant mode."""
        fragment_path = ROOT / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
        assert fragment_path.exists(), f"Missing {fragment_path}"
        content = fragment_path.read_text().lower()
        assert "instant" in content, "AGENTS.fragment.md must mention instant mode"

    def test_gemini_settings_is_valid_json(self) -> None:
        """Gemini settings.json is parseable JSON with mcpServers."""
        settings_path = ROOT / ".gemini" / "settings.json"
        assert settings_path.exists(), f"Missing {settings_path}"
        data = json.loads(settings_path.read_text())
        assert isinstance(data, dict)
        assert "mcpServers" in data

    def test_kimi_mcp_json_is_valid_json(self) -> None:
        """Kimi mcp.json is parseable JSON with mcpServers."""
        mcp_path = ROOT / ".kimi" / "mcp.json"
        assert mcp_path.exists(), f"Missing {mcp_path}"
        data = json.loads(mcp_path.read_text())
        assert isinstance(data, dict)
        assert "mcpServers" in data

    def test_all_host_json_configs_parseable(self) -> None:
        """All JSON host configs remain parseable after changes."""
        json_configs = [
            ROOT / ".claude-plugin" / "plugin.json",
            ROOT / ".gemini" / "settings.json",
            ROOT / ".kimi" / "mcp.json",
        ]
        for cfg in json_configs:
            assert cfg.exists(), f"Missing config: {cfg}"
            try:
                data = json.loads(cfg.read_text())
            except json.JSONDecodeError as exc:
                pytest.fail(f"{cfg.name} is not valid JSON: {exc}")
            assert isinstance(data, dict), f"{cfg.name} root must be an object"

    def test_codex_fragment_is_readable_markdown(self) -> None:
        """Codex AGENTS.fragment.md is non-empty readable markdown."""
        fragment_path = ROOT / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
        assert fragment_path.exists(), f"Missing {fragment_path}"
        content = fragment_path.read_text()
        assert len(content) > 50
        assert content.startswith("#")
