from __future__ import annotations

import json
from unittest.mock import patch

from runtime.providers import ollama_cloud_provider


def test_detect_returns_false_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    provider = ollama_cloud_provider.OllamaCloudProvider()

    assert provider.detect() is False


def test_detect_returns_true_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    provider = ollama_cloud_provider.OllamaCloudProvider()

    assert provider.detect() is True


def test_check_auth_returns_false_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    provider = ollama_cloud_provider.OllamaCloudProvider()

    ok, message = provider.check_auth()

    assert ok is False
    assert "OLLAMA_API_KEY" in message


def test_get_config_path_returns_expected_path() -> None:
    provider = ollama_cloud_provider.OllamaCloudProvider()

    path = provider.get_config_path()

    assert path.endswith(".ollama-cloud/mcp.json")
    assert not path.startswith("~")


def test_write_mcp_config_creates_valid_json(tmp_path) -> None:
    provider = ollama_cloud_provider.OllamaCloudProvider()
    config_path = tmp_path / "mcp.json"

    with patch.object(provider, "get_config_path", return_value=str(config_path)):
        provider.write_mcp_config("http://localhost:8080", server_name="test-server")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["test-server"] == {
        "type": "http",
        "url": "http://localhost:8080",
    }
