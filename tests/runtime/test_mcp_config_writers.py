from __future__ import annotations

import json
from pathlib import Path


def test_mcp_config_writers_write_expected_provider_shapes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime.mcp_config_writers import (
        write_claude_mcp_config,
        write_codex_mcp_config,
        write_gemini_mcp_config,
        write_opencode_mcp_config,
        write_kimi_mcp_config,
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    write_claude_mcp_config(str(project_dir), "http://127.0.0.1:8765/mcp", "omg-memory")
    codex_result = write_codex_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")
    write_gemini_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")
    write_opencode_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")
    write_kimi_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")

    claude_cfg = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))
    assert claude_cfg["mcpServers"]["omg-memory"]["url"] == "http://127.0.0.1:8765/mcp"

    codex_cfg = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert '[mcp_servers.omg-memory]' in codex_cfg
    assert 'url = "http://127.0.0.1:8765/mcp"' in codex_cfg
    assert codex_result["changed"] is True
    assert codex_result["removed_keys"] == []

    gemini_cfg = json.loads((tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    assert gemini_cfg["mcpServers"]["omg-memory"]["httpUrl"] == "http://127.0.0.1:8765/mcp"

    opencode_cfg = json.loads((tmp_path / ".config" / "opencode" / "opencode.json").read_text(encoding="utf-8"))
    assert opencode_cfg["mcp"]["omg-memory"]["url"] == "http://127.0.0.1:8765/mcp"
    assert opencode_cfg["mcp"]["omg-memory"]["type"] == "remote"

    kimi_cfg = json.loads((tmp_path / ".kimi" / "mcp.json").read_text(encoding="utf-8"))
    assert kimi_cfg["mcpServers"]["omg-memory"]["url"] == "http://127.0.0.1:8765/mcp"


def test_write_codex_mcp_config_backs_up_and_removes_incompatible_feature_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime.mcp_config_writers import write_codex_mcp_config

    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        'model = "gpt-5.4"\n'
        "\n"
        "[features]\n"
        "rmcp_client = true\n"
        "unified_exec = true\n",
        encoding="utf-8",
    )

    result = write_codex_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")

    updated = config_path.read_text(encoding="utf-8")
    assert result["changed"] is True
    assert result["removed_keys"] == ["rmcp_client"]
    assert result["backup_path"]
    assert "rmcp_client = true" not in updated
    assert "unified_exec = true" in updated
    assert '[mcp_servers.omg-memory]' in updated
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    backup_text = backup_path.read_text(encoding="utf-8")
    assert "rmcp_client = true" in backup_text


def test_write_codex_mcp_config_is_idempotent_after_repair(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime.mcp_config_writers import write_codex_mcp_config

    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[features]\n"
        "rmcp_client = true\n"
        'unified_exec = true\n'
        '\n'
        '[mcp_servers.omg-memory]\n'
        'type = "http"\n'
        'url = "http://127.0.0.1:8765/mcp"\n',
        encoding="utf-8",
    )

    first = write_codex_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")
    second = write_codex_mcp_config("http://127.0.0.1:8765/mcp", "omg-memory")

    backup_dir = tmp_path / ".codex" / "backups"
    backups = sorted(backup_dir.glob("config.toml.*.bak"))
    assert first["changed"] is True
    assert first["removed_keys"] == ["rmcp_client"]
    assert second["changed"] is False
    assert second["removed_keys"] == []
    assert second["backup_path"] == ""
    assert len(backups) == 1
