"""Tests for tools.lsp_client — mock-based, no real LSP server needed."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tools.lsp_client import LSPClient


class TestStubMode:
    """When server_cmd is None, client should be inert but instantiable."""

    def test_instantiation_no_args(self):
        client = LSPClient()
        assert client is not None

    def test_start_returns_false(self):
        client = LSPClient()
        assert client.start() is False

    def test_is_connected_returns_false(self):
        client = LSPClient()
        assert client.is_connected() is False

    def test_send_request_returns_none(self):
        client = LSPClient()
        result = client.send_request("textDocument/completion", {})
        assert result is None

    def test_send_notification_does_not_raise(self):
        client = LSPClient()
        client.send_notification("initialized", {})

    def test_initialize_returns_empty_dict(self):
        client = LSPClient()
        result = client.initialize("file:///tmp")
        assert result == {}

    def test_shutdown_does_not_raise(self):
        client = LSPClient()
        client.shutdown()

    def test_repr_shows_stub(self):
        client = LSPClient()
        assert "(stub)" in repr(client)

    def test_context_manager(self):
        with LSPClient() as client:
            assert client.is_connected() is False


class TestTransportValidation:
    def test_unsupported_transport_raises(self):
        with pytest.raises(ValueError, match="Unsupported transport"):
            LSPClient(server_cmd=["fake"], transport="tcp")

    def test_stdio_transport_accepted(self):
        client = LSPClient(server_cmd=["fake"], transport="stdio")
        assert client is not None


class TestMessageEncoding:
    """Verify JSON-RPC 2.0 framing with Content-Length header."""

    def test_encode_request(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        raw = LSPClient.encode_message(body)

        header, payload = raw.split(b"\r\n\r\n", 1)
        assert header.startswith(b"Content-Length: ")

        content_length = int(header.split(b": ")[1])
        assert content_length == len(payload)

        decoded = json.loads(payload)
        assert decoded["jsonrpc"] == "2.0"
        assert decoded["id"] == 1
        assert decoded["method"] == "initialize"

    def test_encode_notification(self):
        body = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        raw = LSPClient.encode_message(body)

        _, payload = raw.split(b"\r\n\r\n", 1)
        decoded = json.loads(payload)
        assert "id" not in decoded
        assert decoded["method"] == "initialized"

    def test_content_length_matches_payload_bytes(self):
        body = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": {"key": "value"}}
        raw = LSPClient.encode_message(body)

        header_end = raw.index(b"\r\n\r\n")
        header = raw[:header_end].decode("ascii")
        payload = raw[header_end + 4:]

        length_str = header.replace("Content-Length: ", "")
        assert int(length_str) == len(payload)

    def test_unicode_in_params(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {"text": "日本語"}}
        raw = LSPClient.encode_message(body)

        _, payload = raw.split(b"\r\n\r\n", 1)
        assert len(payload) > len("日本語")

        header = raw.split(b"\r\n\r\n")[0].decode("ascii")
        content_length = int(header.split(": ")[1])
        assert content_length == len(payload)


class TestWithMockProcess:
    """Tests that use a mock subprocess to simulate a running server."""

    @staticmethod
    def _make_response(result: dict, req_id: int = 1) -> bytes:
        body = {"jsonrpc": "2.0", "id": req_id, "result": result}
        return LSPClient.encode_message(body)

    @staticmethod
    def _make_error_response(error: dict, req_id: int = 1) -> bytes:
        body = {"jsonrpc": "2.0", "id": req_id, "error": error}
        return LSPClient.encode_message(body)

    def _create_mock_process(self, response_bytes: bytes | None = None) -> MagicMock:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process alive
        mock_proc.pid = 12345
        mock_proc.stdin = MagicMock()

        if response_bytes is not None:
            mock_proc.stdout = BytesIO(response_bytes)
        else:
            mock_proc.stdout = BytesIO(b"")

        mock_proc.stderr = BytesIO(b"")
        return mock_proc

    @patch("tools.lsp_client.subprocess.Popen")
    def test_start_success(self, mock_popen):
        mock_popen.return_value = self._create_mock_process()

        client = LSPClient(server_cmd=["fake-lsp"])
        assert client.start() is True
        assert client.is_connected() is True

    @patch("tools.lsp_client.subprocess.Popen")
    def test_start_failure(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("no such file")

        client = LSPClient(server_cmd=["nonexistent-lsp"])
        assert client.start() is False
        assert client.is_connected() is False

    @patch("tools.lsp_client.subprocess.Popen")
    def test_send_request_with_response(self, mock_popen):
        response = self._make_response({"capabilities": {}})
        mock_proc = self._create_mock_process(response)
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()

        result = client.send_request("initialize", {"rootUri": "file:///tmp"})
        assert result == {"capabilities": {}}

    @patch("tools.lsp_client.subprocess.Popen")
    def test_send_request_error_response_returns_none(self, mock_popen):
        response = self._make_error_response({"code": -32600, "message": "Invalid Request"})
        mock_proc = self._create_mock_process(response)
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()

        result = client.send_request("bad/method", {})
        assert result is None

    @patch("tools.lsp_client.subprocess.Popen")
    def test_send_request_timeout_returns_none(self, mock_popen):
        mock_proc = self._create_mock_process(b"")
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"], timeout=0.1)
        client.start()

        result = client.send_request("textDocument/hover", {})
        assert result is None

    @patch("tools.lsp_client.subprocess.Popen")
    def test_send_notification_writes_to_stdin(self, mock_popen):
        mock_proc = self._create_mock_process()
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()
        client.send_notification("initialized", {})

        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        assert b"Content-Length:" in written
        assert b'"initialized"' in written

    @patch("tools.lsp_client.subprocess.Popen")
    def test_request_id_increments(self, mock_popen):
        response1 = self._make_response({"result": "a"}, req_id=1)
        response2 = self._make_response({"result": "b"}, req_id=2)

        mock_proc = self._create_mock_process(response1 + response2)
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()

        client.send_request("method1", {})

        written_calls = mock_proc.stdin.write.call_args_list
        first_msg = json.loads(written_calls[0][0][0].split(b"\r\n\r\n", 1)[1])
        assert first_msg["id"] == 1

        mock_proc.stdout = BytesIO(response2)
        client.send_request("method2", {})

        written_calls = mock_proc.stdin.write.call_args_list
        second_msg = json.loads(written_calls[1][0][0].split(b"\r\n\r\n", 1)[1])
        assert second_msg["id"] == 2

    @patch("tools.lsp_client.subprocess.Popen")
    def test_is_connected_false_after_process_exits(self, mock_popen):
        mock_proc = self._create_mock_process()
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()
        assert client.is_connected() is True

        mock_proc.poll.return_value = 0  # process exited
        assert client.is_connected() is False

    @patch("tools.lsp_client.subprocess.Popen")
    def test_shutdown_calls_terminate(self, mock_popen):
        mock_proc = self._create_mock_process()
        mock_proc.stdout = BytesIO(b"")  # shutdown won't get a real response
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"], timeout=0.1)
        client.start()
        client.shutdown()

        mock_proc.terminate.assert_called_once()
        assert client.is_connected() is False

    @patch("tools.lsp_client.subprocess.Popen")
    def test_initialize_handshake(self, mock_popen):
        caps = {"textDocumentSync": 1}
        response = self._make_response({"capabilities": caps})
        mock_proc = self._create_mock_process(response)
        mock_popen.return_value = mock_proc

        client = LSPClient(server_cmd=["fake-lsp"])
        client.start()

        result = client.initialize("file:///project")
        assert result == {"capabilities": caps}

        writes = mock_proc.stdin.write.call_args_list
        init_msg = json.loads(writes[0][0][0].split(b"\r\n\r\n", 1)[1])
        assert init_msg["method"] == "initialize"
        assert init_msg["params"]["rootUri"] == "file:///project"

    @patch("tools.lsp_client.subprocess.Popen")
    def test_repr_with_command(self, mock_popen):
        mock_popen.return_value = self._create_mock_process()

        client = LSPClient(server_cmd=["pyright-langserver", "--stdio"])
        client.start()
        r = repr(client)
        assert "pyright-langserver" in r
        assert "connected=True" in r
