from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import cast

import pytest

from runtime.providers.opencode_provider import OpenCodeProvider


def test_provider_name() -> None:
    provider = OpenCodeProvider()
    assert provider.get_name() == "opencode"


def test_provider_config_path() -> None:
    provider = OpenCodeProvider()
    assert provider.get_config_path().endswith("opencode.json")


def test_provider_detect_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenCodeProvider()

    def _missing(_name: str, _mode: int = 0, _path: str | None = None) -> None:
        return None

    monkeypatch.setattr(shutil, "which", _missing)
    assert provider.detect() is False


def test_check_auth_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider = OpenCodeProvider()
    missing = tmp_path / "missing" / "auth.json"

    def _auth_path(_path: str) -> str:
        return str(missing)

    monkeypatch.setattr(os.path, "expanduser", _auth_path)

    ok, message = provider.check_auth()

    assert ok is False
    assert message.startswith("auth not found:")


def test_check_auth_valid_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider = OpenCodeProvider()
    auth_path = tmp_path / "auth.json"
    _ = auth_path.write_text(json.dumps({"token": "abc"}))

    def _auth_path(_path: str) -> str:
        return str(auth_path)

    monkeypatch.setattr(os.path, "expanduser", _auth_path)

    ok, message = provider.check_auth()

    assert ok is True
    assert message == "auth found"


def test_get_project_config_path(tmp_path: Path) -> None:
    provider = OpenCodeProvider()
    path = provider.get_project_config_path(str(tmp_path))
    assert path.endswith("opencode.json")


def test_get_plugin_dir(tmp_path: Path) -> None:
    provider = OpenCodeProvider()
    path = provider.get_plugin_dir(str(tmp_path))
    assert path.endswith(".opencode/plugins")


def test_write_mcp_config_uses_mcp_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider = OpenCodeProvider()
    config_path = tmp_path / "opencode.json"

    def _config_path(_path: str) -> str:
        return str(config_path)

    monkeypatch.setattr(os.path, "expanduser", _config_path)

    provider.write_mcp_config("http://localhost:8080", server_name="memory-server")

    data = cast(dict[str, object], json.loads(config_path.read_text()))
    assert "mcp" in data
    assert "mcpServers" not in data
