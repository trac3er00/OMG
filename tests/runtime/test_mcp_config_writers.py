from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from runtime.mcp_config_writers import (
    write_claude_mcp_config,
    write_codex_mcp_config,
    write_gemini_mcp_config,
    write_kimi_mcp_config,
    write_opencode_mcp_config,
)


def _read_json(path: Path) -> dict[str, object]:
    parsed = cast(object, json.loads(path.read_text()))
    assert isinstance(parsed, dict)
    return cast(dict[str, object], parsed)


def _as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_write_claude_mcp_config_merges_and_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / ".mcp.json"
    _ = config_path.write_text(
        json.dumps(
            {
                "projectName": "demo",
                "mcpServers": {
                    "existing-server": {
                        "command": "npx",
                        "args": ["-y", "@example/server"],
                    }
                },
            }
        )
    )

    write_claude_mcp_config(str(tmp_path), "http://localhost:8765")
    first_data = _read_json(config_path)
    first_servers = _as_dict(first_data["mcpServers"])

    assert first_data["projectName"] == "demo"
    assert "existing-server" in first_servers
    assert first_servers["memory-server"] == {
        "type": "http",
        "url": "http://localhost:8765",
    }

    write_claude_mcp_config(str(tmp_path), "http://localhost:8765")
    second_data = _read_json(config_path)

    assert second_data == first_data


def test_write_codex_mcp_config_preserves_comments_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = config_path.write_text(
        "# user config\n"
        + "# keep this comment\n"
        + "[mcp_servers.existing-server]\n"
        + 'type = "http"\n'
        + 'url = "http://localhost:7777"\n'
    )

    write_codex_mcp_config("http://localhost:8765")
    first_text = config_path.read_text()

    assert "# user config" in first_text
    assert "# keep this comment" in first_text
    assert "[mcp_servers.existing-server]" in first_text
    assert '[mcp_servers.memory-server]' in first_text
    assert 'url = "http://localhost:8765"' in first_text
    assert 'type = "http"' in first_text

    write_codex_mcp_config("http://localhost:8765")
    second_text = config_path.read_text()

    assert second_text.count("[mcp_servers.memory-server]") == 1
    assert second_text == first_text


def test_write_gemini_mcp_config_merges_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".gemini" / "settings.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = config_path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "mcpServers": {
                    "existing-server": {"httpUrl": "http://localhost:1111"}
                },
            }
        )
    )

    write_gemini_mcp_config("http://localhost:8765")
    first_data = _read_json(config_path)
    first_servers = _as_dict(first_data["mcpServers"])
    assert first_data["theme"] == "dark"
    assert "existing-server" in first_servers
    assert first_servers["memory-server"] == {
        "httpUrl": "http://localhost:8765"
    }

    write_gemini_mcp_config("http://localhost:8765")
    second_data = _read_json(config_path)
    assert second_data == first_data


def test_write_opencode_mcp_config_merges_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".config" / "opencode" / "opencode.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = config_path.write_text(
        json.dumps(
            {
                "telemetry": True,
                "mcp": {
                    "existing-server": {
                        "type": "remote",
                        "url": "http://localhost:2222",
                    }
                },
            }
        )
    )

    write_opencode_mcp_config("http://localhost:8765")
    first_data = _read_json(config_path)
    first_servers = _as_dict(first_data["mcp"])
    assert first_data["telemetry"] is True
    assert "existing-server" in first_servers
    assert first_servers["memory-server"] == {
        "type": "remote",
        "url": "http://localhost:8765",
    }

    write_opencode_mcp_config("http://localhost:8765")
    second_data = _read_json(config_path)
    assert second_data == first_data


def test_write_kimi_mcp_config_merges_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".kimi" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = config_path.write_text(
        json.dumps(
            {
                "prefs": {"language": "en"},
                "mcpServers": {
                    "existing-server": {
                        "type": "http",
                        "url": "http://localhost:3333",
                    }
                },
            }
        )
    )

    write_kimi_mcp_config("http://localhost:8765")
    first_data = _read_json(config_path)
    prefs = _as_dict(first_data["prefs"])
    first_servers = _as_dict(first_data["mcpServers"])
    assert prefs["language"] == "en"
    assert "existing-server" in first_servers
    assert first_servers["memory-server"] == {
        "type": "http",
        "url": "http://localhost:8765",
    }

    write_kimi_mcp_config("http://localhost:8765")
    second_data = _read_json(config_path)
    assert second_data == first_data
