"""Tests for tools.lsp_operations — mock-based, no real LSP server needed."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from tools.lsp_operations import (
    _is_enabled,
    _normalize_locations,
    get_client,
    lsp_code_actions,
    lsp_definition,
    lsp_diagnostics,
    lsp_hover,
    lsp_implementation,
    lsp_references,
    lsp_reload,
    lsp_rename,
    lsp_status,
    lsp_symbols,
    lsp_type_definition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENABLE_ENV = {"OMG_LSP_TOOLS_ENABLED": "1"}
_DISABLE_ENV = {"OMG_LSP_TOOLS_ENABLED": "0"}


# ---------------------------------------------------------------------------
# Feature flag & get_client
# ---------------------------------------------------------------------------

class TestIsEnabled:
    @patch.dict(os.environ, _ENABLE_ENV)
    def test_enabled_via_env(self):
        assert _is_enabled() is True

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_disabled_via_env(self):
        assert _is_enabled() is False

    @patch.dict(os.environ, {}, clear=False)
    def test_default_disabled(self):
        # Remove key if present
        os.environ.pop("OMG_LSP_TOOLS_ENABLED", None)
        assert _is_enabled() is False


class TestGetClient:
    @patch.dict(os.environ, _DISABLE_ENV)
    def test_raises_when_disabled(self):
        with pytest.raises(RuntimeError, match="LSP tools are disabled"):
            get_client()

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client", new=None)
    def test_creates_client_when_none(self):
        client = get_client()
        assert client is not None

    @patch.dict(os.environ, _ENABLE_ENV)
    def test_returns_existing_client(self):
        mock = MagicMock()
        with patch("tools.lsp_operations._client", mock):
            result = get_client()
            assert result is mock


# ---------------------------------------------------------------------------
# Feature flag disabled → graceful defaults
# ---------------------------------------------------------------------------

class TestFeatureFlagDisabled:
    """Every operation returns its graceful default when flag is off."""

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_diagnostics_disabled(self):
        assert lsp_diagnostics("/tmp/test.py") == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_definition_disabled(self):
        assert lsp_definition("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_type_definition_disabled(self):
        assert lsp_type_definition("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_implementation_disabled(self):
        assert lsp_implementation("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_references_disabled(self):
        assert lsp_references("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_hover_disabled(self):
        assert lsp_hover("/tmp/test.py", 1, 0) is None

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_symbols_disabled(self):
        assert lsp_symbols("/tmp/test.py") == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_rename_disabled(self):
        assert lsp_rename("/tmp/test.py", 1, 0, "new") == {}

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_code_actions_disabled(self):
        assert lsp_code_actions("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_status_disabled(self):
        result = lsp_status()
        assert result["connected"] is False
        assert result["server_name"] is None
        assert result["capabilities"] == {}

    @patch.dict(os.environ, _DISABLE_ENV)
    def test_reload_disabled(self):
        assert lsp_reload() is False


# ---------------------------------------------------------------------------
# Operations with mocked client (enabled)
# ---------------------------------------------------------------------------

class TestLspDiagnostics:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_parsed_diagnostics(self, mock_client):
        mock_client.send_request.return_value = {
            "kind": "full",
            "items": [
                {
                    "severity": 1,
                    "message": "Undefined variable 'x'",
                    "range": {
                        "start": {"line": 5, "character": 0},
                        "end": {"line": 5, "character": 1},
                    },
                },
                {
                    "severity": 2,
                    "message": "Unused import",
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 10},
                    },
                },
            ],
        }
        result = lsp_diagnostics("/tmp/test.py")
        assert len(result) == 2
        assert result[0]["severity"] == "error"
        assert result[0]["message"] == "Undefined variable 'x'"
        assert result[1]["severity"] == "warning"

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_empty_on_none(self, mock_client):
        mock_client.send_request.return_value = None
        assert lsp_diagnostics("/tmp/test.py") == []


class TestLspDefinition:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_location_list(self, mock_client):
        mock_client.send_request.return_value = [
            {
                "uri": "file:///project/mod.py",
                "range": {"start": {"line": 10, "character": 4}},
            }
        ]
        result = lsp_definition("/tmp/test.py", 5, 10)
        assert len(result) == 1
        assert result[0]["uri"] == "file:///project/mod.py"

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_single_location_dict(self, mock_client):
        mock_client.send_request.return_value = {
            "uri": "file:///project/mod.py",
            "range": {"start": {"line": 1, "character": 0}},
        }
        result = lsp_definition("/tmp/test.py", 5, 10)
        assert len(result) == 1


class TestLspTypeDefinition:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_locations(self, mock_client):
        mock_client.send_request.return_value = [
            {"uri": "file:///types.py", "range": {}}
        ]
        result = lsp_type_definition("/tmp/test.py", 3, 5)
        assert len(result) == 1
        assert result[0]["uri"] == "file:///types.py"


class TestLspImplementation:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_locations(self, mock_client):
        mock_client.send_request.return_value = [
            {"uri": "file:///impl.py", "range": {}}
        ]
        result = lsp_implementation("/tmp/test.py", 7, 0)
        assert len(result) == 1
        assert result[0]["uri"] == "file:///impl.py"


class TestLspReferences:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_references(self, mock_client):
        mock_client.send_request.return_value = [
            {"uri": "file:///a.py", "range": {}},
            {"uri": "file:///b.py", "range": {}},
        ]
        result = lsp_references("/tmp/test.py", 2, 4)
        assert len(result) == 2

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_include_declaration_param(self, mock_client):
        mock_client.send_request.return_value = []
        lsp_references("/tmp/test.py", 2, 4, include_declaration=False)
        call_args = mock_client.send_request.call_args
        params = call_args[0][1]
        assert params["context"]["includeDeclaration"] is False


class TestLspHover:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_string_contents(self, mock_client):
        mock_client.send_request.return_value = {"contents": "def foo(): ..."}
        result = lsp_hover("/tmp/test.py", 1, 0)
        assert result == "def foo(): ..."

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_markup_content(self, mock_client):
        mock_client.send_request.return_value = {
            "contents": {"kind": "markdown", "value": "**bold** text"}
        }
        result = lsp_hover("/tmp/test.py", 1, 0)
        assert result == "**bold** text"

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_list_contents(self, mock_client):
        mock_client.send_request.return_value = {
            "contents": ["line1", {"value": "line2"}]
        }
        result = lsp_hover("/tmp/test.py", 1, 0)
        assert result == "line1\nline2"

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_none_on_no_result(self, mock_client):
        mock_client.send_request.return_value = None
        assert lsp_hover("/tmp/test.py", 1, 0) is None


class TestLspSymbols:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_symbols(self, mock_client):
        mock_client.send_request.return_value = [
            {
                "name": "MyClass",
                "kind": 5,
                "range": {"start": {"line": 0, "character": 0}},
            },
            {
                "name": "my_func",
                "kind": 12,
                "range": {"start": {"line": 10, "character": 0}},
            },
        ]
        result = lsp_symbols("/tmp/test.py")
        assert len(result) == 2
        assert result[0]["name"] == "MyClass"
        assert result[0]["kind"] == "Class"
        assert result[1]["kind"] == "Function"


class TestLspRename:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_workspace_edit(self, mock_client):
        workspace_edit = {
            "changes": {
                "file:///test.py": [
                    {
                        "range": {"start": {"line": 1, "character": 4}},
                        "newText": "new_name",
                    }
                ]
            }
        }
        mock_client.send_request.return_value = workspace_edit
        result = lsp_rename("/tmp/test.py", 1, 4, "new_name")
        assert "changes" in result

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_new_name_in_params(self, mock_client):
        mock_client.send_request.return_value = {}
        lsp_rename("/tmp/test.py", 1, 4, "bar")
        call_args = mock_client.send_request.call_args
        params = call_args[0][1]
        assert params["newName"] == "bar"


class TestLspCodeActions:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_returns_actions(self, mock_client):
        mock_client.send_request.return_value = [
            {"title": "Import os", "kind": "quickfix"},
            {"title": "Extract variable", "kind": "refactor.extract"},
        ]
        result = lsp_code_actions("/tmp/test.py", 1, 0)
        assert len(result) == 2
        assert result[0]["title"] == "Import os"
        assert result[1]["kind"] == "refactor.extract"


class TestLspStatus:
    @patch.dict(os.environ, _ENABLE_ENV)
    def test_no_client_returns_disconnected(self):
        with patch("tools.lsp_operations._client", None):
            result = lsp_status()
            assert result["connected"] is False

    @patch.dict(os.environ, _ENABLE_ENV)
    def test_connected_client(self):
        mock = MagicMock()
        mock.is_connected.return_value = True
        with patch("tools.lsp_operations._client", mock):
            result = lsp_status()
            assert result["connected"] is True


class TestLspReload:
    @patch.dict(os.environ, _ENABLE_ENV)
    def test_reload_creates_new_client(self):
        with patch("tools.lsp_operations._client", None):
            result = lsp_reload()
            assert result is True

    @patch.dict(os.environ, _ENABLE_ENV)
    def test_reload_shuts_down_existing(self):
        old_client = MagicMock()
        with patch("tools.lsp_operations._client", old_client):
            result = lsp_reload()
            assert result is True
            old_client.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling → graceful defaults
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_send_request_exception_returns_empty(self, mock_client):
        mock_client.send_request.side_effect = ConnectionError("server died")
        assert lsp_diagnostics("/tmp/test.py") == []
        assert lsp_definition("/tmp/test.py", 1, 0) == []
        assert lsp_hover("/tmp/test.py", 1, 0) is None
        assert lsp_symbols("/tmp/test.py") == []
        assert lsp_rename("/tmp/test.py", 1, 0, "x") == {}
        assert lsp_code_actions("/tmp/test.py", 1, 0) == []

    @patch.dict(os.environ, _ENABLE_ENV)
    @patch("tools.lsp_operations._client")
    def test_unexpected_result_shape(self, mock_client):
        # Non-list, non-dict, non-None result
        mock_client.send_request.return_value = 42
        assert lsp_symbols("/tmp/test.py") == []
        assert lsp_code_actions("/tmp/test.py", 1, 0) == []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestNormalizeLocations:
    def test_none_returns_empty(self):
        assert _normalize_locations(None) == []

    def test_single_dict(self):
        loc = {"uri": "file:///x.py", "range": {}}
        result = _normalize_locations(loc)
        assert len(result) == 1
        assert result[0]["uri"] == "file:///x.py"

    def test_location_link_format(self):
        link = {"targetUri": "file:///y.py", "targetRange": {"start": {"line": 0}}}
        result = _normalize_locations([link])
        assert result[0]["uri"] == "file:///y.py"
        assert result[0]["range"] == {"start": {"line": 0}}
