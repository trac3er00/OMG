from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from runtime.mcp_config_writers import (
    get_managed_python_path,
    write_claude_mcp_config,
    write_claude_mcp_stdio_config,
    write_codex_mcp_config,
    write_codex_mcp_stdio_config,
    write_gemini_mcp_config,
    write_gemini_mcp_stdio_config,
    write_kimi_mcp_config,
    write_kimi_mcp_stdio_config,
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


def test_write_codex_mcp_config_rejects_invalid_server_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    with pytest.raises(ValueError, match="server_name"):
        write_codex_mcp_config("http://localhost:8765", 'evil"]\n[mcp_servers.bad]')


def test_write_codex_mcp_config_rejects_invalid_server_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    with pytest.raises(ValueError, match="server_url"):
        write_codex_mcp_config('http://localhost:8765"\n[mcp_servers.bad]\nurl="http://evil"')


def test_write_claude_mcp_config_rejects_invalid_server_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="server_name"):
        write_claude_mcp_config(str(tmp_path), "http://localhost:8765", "../escape")


def test_write_claude_mcp_stdio_config_merges_command_entry(tmp_path: Path) -> None:
    write_claude_mcp_stdio_config(
        str(tmp_path),
        server_name="omg-control",
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
    )
    config_path = tmp_path / ".mcp.json"
    payload = _read_json(config_path)
    servers = _as_dict(payload["mcpServers"])
    assert servers["omg-control"] == {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"],
    }


def test_write_codex_mcp_stdio_config_writes_toml_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    write_codex_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
    )
    config_path = tmp_path / ".codex" / "config.toml"
    content = config_path.read_text()
    assert '[mcp_servers.omg-control]' in content
    assert 'command = "python3"' in content
    assert 'args = ["-m", "runtime.omg_mcp_server"]' in content


def test_write_gemini_and_kimi_mcp_stdio_config_merge_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    write_gemini_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
    )
    write_kimi_mcp_stdio_config(
        command="python3",
        args=["-m", "runtime.omg_mcp_server"],
        server_name="omg-control",
    )

    gemini = _read_json(tmp_path / ".gemini" / "settings.json")
    kimi = _read_json(tmp_path / ".kimi" / "mcp.json")
    assert _as_dict(gemini["mcpServers"])["omg-control"] == {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"],
    }
    assert _as_dict(kimi["mcpServers"])["omg-control"] == {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"],
    }


def test_get_managed_python_path_returns_venv_path(tmp_path: Path) -> None:
    result = get_managed_python_path(str(tmp_path / ".claude"))
    expected = str(tmp_path / ".claude" / "omg-runtime" / ".venv" / "bin" / "python")
    assert result == expected


def test_get_managed_python_path_falls_back_to_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    result = get_managed_python_path()
    expected = str(tmp_path / ".claude" / "omg-runtime" / ".venv" / "bin" / "python")
    assert result == expected


def test_managed_python_path_in_claude_stdio_config(tmp_path: Path) -> None:
    managed_python = get_managed_python_path(str(tmp_path / ".claude"))
    write_claude_mcp_stdio_config(
        str(tmp_path),
        server_name="omg-control",
        command=managed_python,
        args=["-m", "runtime.omg_mcp_server"],
    )
    config_path = tmp_path / ".mcp.json"
    payload = _read_json(config_path)
    servers = _as_dict(payload["mcpServers"])
    assert servers["omg-control"] == {
        "command": managed_python,
        "args": ["-m", "runtime.omg_mcp_server"],
    }
    assert "omg-runtime/.venv/bin/python" in managed_python


# -- Preset surface narrowing ----------------------------------------

from hooks.setup_wizard import get_default_mcps_for_preset, select_mcps, configure_mcp


def test_safe_preset_returns_only_filesystem_and_control() -> None:
    ids = get_default_mcps_for_preset("safe")
    assert set(ids) == {"filesystem", "omg-control"}


def test_balanced_preset_adds_context7_only() -> None:
    ids = get_default_mcps_for_preset("balanced")
    assert set(ids) == {"filesystem", "omg-control", "context7"}


def test_safe_preset_omits_http_memory_websearch_browser() -> None:
    ids = get_default_mcps_for_preset("safe")
    for excluded in ("omg-memory", "websearch", "chrome-devtools"):
        assert excluded not in ids, f"{excluded} must not appear in safe preset"


def test_balanced_preset_omits_http_memory_websearch_browser() -> None:
    ids = get_default_mcps_for_preset("balanced")
    for excluded in ("omg-memory", "websearch", "chrome-devtools"):
        assert excluded not in ids, f"{excluded} must not appear in balanced preset"


def test_interop_preset_includes_http_memory_and_websearch() -> None:
    ids = get_default_mcps_for_preset("interop")
    assert "omg-memory" in ids
    assert "websearch" in ids
    assert "chrome-devtools" not in ids


def test_labs_preset_includes_browser() -> None:
    ids = get_default_mcps_for_preset("labs")
    assert "chrome-devtools" in ids
    assert "omg-memory" in ids


def test_select_mcps_safe_preset_produces_minimal_config() -> None:
    config = select_mcps(preset="safe")
    server_names = set(config["mcpServers"].keys())
    assert server_names == {"filesystem", "omg-control"}


def test_select_mcps_balanced_preset_adds_context7() -> None:
    config = select_mcps(preset="balanced")
    server_names = set(config["mcpServers"].keys())
    assert server_names == {"filesystem", "omg-control", "context7"}


def test_configure_mcp_safe_preset_skips_http_memory(tmp_path: Path) -> None:
    result = configure_mcp(
        str(tmp_path),
        detected_clis={},
        preset="safe",
    )
    assert result["status"] == "ok"
    config_path = tmp_path / ".mcp.json"
    payload = _read_json(config_path)
    servers = _as_dict(payload["mcpServers"])
    assert "omg-control" in servers
    assert "omg-memory" not in servers
    assert "memory-server" not in servers


def test_configure_mcp_interop_preset_writes_http_memory(tmp_path: Path) -> None:
    result = configure_mcp(
        str(tmp_path),
        detected_clis={},
        preset="interop",
    )
    assert result["status"] == "ok"
    config_path = tmp_path / ".mcp.json"
    payload = _read_json(config_path)
    servers = _as_dict(payload["mcpServers"])
    assert "omg-control" in servers
    assert "omg-memory" in servers
