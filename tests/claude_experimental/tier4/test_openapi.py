"""Tests for claude_experimental.integration.openapi_gen — ToolGenerator."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.fixture
def sample_spec() -> dict:
    """Minimal valid OpenAPI spec with two endpoints."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {
                    "operationId": "list_users",
                    "parameters": [
                        {"name": "limit", "in": "query"},
                    ],
                }
            },
            "/users/{user_id}": {
                "get": {
                    "operationId": "get_user",
                    "parameters": [
                        {"name": "user_id", "in": "path"},
                    ],
                }
            },
        },
    }


@pytest.fixture
def spec_file(tmp_path, sample_spec) -> str:
    """Write sample spec to a JSON file and return the path."""
    path = tmp_path / "api.json"
    path.write_text(json.dumps(sample_spec), encoding="utf-8")
    return str(path)


@pytest.mark.experimental
class TestToolGeneratorGenerate:
    """Tests for ToolGenerator.generate()."""

    def test_generate_produces_callables(self, spec_file):
        """generate() returns a dict of callable endpoint functions."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        gen = ToolGenerator()
        tools = gen.generate(spec_file)

        assert isinstance(tools, dict)
        assert "list_users" in tools
        assert "get_user" in tools
        assert callable(tools["list_users"])
        assert callable(tools["get_user"])

    def test_generated_function_name(self, spec_file):
        """Generated callables have correct __name__."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        gen = ToolGenerator()
        tools = gen.generate(spec_file)
        assert tools["list_users"].__name__ == "list_users"
        assert tools["get_user"].__name__ == "get_user"

    @patch("claude_experimental.integration.openapi_gen.request.urlopen")
    def test_generated_callable_invocation(self, mock_urlopen, spec_file):
        """Generated callable makes HTTP request and returns parsed JSON."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [{"id": 1, "name": "Alice"}]
        ).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        gen = ToolGenerator()
        tools = gen.generate(spec_file)
        result = tools["list_users"]("http://example.com", limit=10)

        # Non-dict JSON is wrapped in {"data": ...}
        assert "data" in result
        mock_urlopen.assert_called_once()

    @patch("claude_experimental.integration.openapi_gen.request.urlopen")
    def test_404_raises_file_not_found(self, mock_urlopen, spec_file):
        """HTTPError 404 is mapped to FileNotFoundError."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        mock_urlopen.side_effect = HTTPError(
            url="http://example.com/users/999",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

        gen = ToolGenerator()
        tools = gen.generate(spec_file)

        with pytest.raises(FileNotFoundError, match="404"):
            tools["get_user"]("http://example.com", "999")


@pytest.mark.experimental
class TestToolGeneratorEdgeCases:
    """Edge case tests for ToolGenerator."""

    def test_malformed_spec_raises_value_error(self, tmp_path):
        """Non-object JSON root raises ValueError."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        bad_spec = tmp_path / "bad.json"
        bad_spec.write_text('"not an object"', encoding="utf-8")

        gen = ToolGenerator()
        with pytest.raises(ValueError, match="root must be an object"):
            gen.generate(str(bad_spec))

    def test_empty_paths_produces_no_tools(self, tmp_path):
        """Spec with empty paths produces empty dict."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        spec = {"openapi": "3.0.0", "info": {"title": "Empty"}, "paths": {}}
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(spec), encoding="utf-8")

        gen = ToolGenerator()
        tools = gen.generate(str(path))
        assert tools == {}

    def test_disabled_flag_raises_runtime_error(self, monkeypatch):
        """ToolGenerator.generate() raises RuntimeError when flag is disabled."""
        from claude_experimental.integration.openapi_gen import ToolGenerator

        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")

        gen = ToolGenerator()
        with pytest.raises(RuntimeError, match="disabled"):
            gen.generate("nonexistent.json")


@pytest.fixture
def auth_spec() -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "Auth API", "version": "1.0.0"},
        "paths": {
            "/secure": {
                "get": {
                    "operationId": "get_secure",
                    "parameters": [
                        {"name": "Authorization", "in": "header"},
                        {"name": "limit", "in": "query"},
                    ],
                }
            }
        },
    }


@pytest.fixture
def auth_spec_file(tmp_path, auth_spec) -> str:
    path = tmp_path / "auth_api.json"
    path.write_text(json.dumps(auth_spec), encoding="utf-8")
    return str(path)


@pytest.mark.experimental
class TestHeaderParamRouting:

    @patch("claude_experimental.integration.openapi_gen.request.urlopen")
    def test_header_param_sent_as_request_header(self, mock_urlopen, auth_spec_file):
        from claude_experimental.integration.openapi_gen import ToolGenerator

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"ok": True}).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        gen = ToolGenerator()
        tools = gen.generate(auth_spec_file)
        tools["get_secure"]("http://example.com", Authorization="Bearer tok", limit=10)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer tok"
        assert "Authorization=" not in req.full_url

    @patch("claude_experimental.integration.openapi_gen.request.urlopen")
    def test_header_param_not_in_url(self, mock_urlopen, auth_spec_file):
        from claude_experimental.integration.openapi_gen import ToolGenerator

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"ok": True}).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        gen = ToolGenerator()
        tools = gen.generate(auth_spec_file)
        tools["get_secure"]("http://example.com", Authorization="Bearer tok", limit=10)

        req = mock_urlopen.call_args[0][0]
        assert "limit=10" in req.full_url
        assert "Authorization" not in req.full_url
