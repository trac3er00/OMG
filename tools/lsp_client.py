"""LSP client wrapper supporting stdio transport.

Implements JSON-RPC 2.0 over stdio with Content-Length framing
per the Language Server Protocol specification.

Pure stdlib: subprocess, json, threading — no external dependencies.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from typing import Any

logger = logging.getLogger(__name__)

_CONTENT_LENGTH_HEADER = "Content-Length: "
_HEADER_SEPARATOR = "\r\n\r\n"
_DEFAULT_TIMEOUT = 10.0


class LSPClient:
    """LSP client that communicates with a language server over stdio.

    When ``server_cmd`` is None the client operates in **stub mode**:
    ``start()`` returns False, ``is_connected()`` returns False, and
    ``send_request()`` returns None.  This allows OMG to instantiate
    the client unconditionally — LSP is always optional.
    """

    def __init__(
        self,
        server_cmd: list[str] | None = None,
        transport: str = "stdio",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if transport != "stdio":
            raise ValueError(f"Unsupported transport: {transport!r} (only 'stdio' is supported)")

        self._server_cmd = server_cmd
        self._transport = transport
        self._timeout = timeout

        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._connected = False
        self._initialized = False

    def start(self) -> bool:
        """Start the language-server process.

        Returns True on success, False if no server command was
        configured (stub mode) or if the process failed to launch.
        """
        if self._server_cmd is None:
            logger.debug("LSPClient in stub mode — no server_cmd provided")
            return False

        try:
            self._process = subprocess.Popen(
                self._server_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._connected = True
            logger.info("LSP server started: %s (pid=%d)", self._server_cmd, self._process.pid)
            return True
        except (OSError, FileNotFoundError) as exc:
            logger.error("Failed to start LSP server %s: %s", self._server_cmd, exc)
            self._connected = False
            return False

    def initialize(
        self,
        root_uri: str,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform the LSP ``initialize`` handshake.

        Returns the server capabilities dict, or an empty dict on
        failure / stub mode.
        """
        if not self._connected:
            return {}

        params: dict[str, Any] = {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": capabilities or {},
        }

        result = self.send_request("initialize", params)
        if result is None:
            return {}

        self.send_notification("initialized", {})
        self.send_notification("initialized", {})
        self._initialized = True
        return result

    def shutdown(self) -> None:
        """Send ``shutdown`` then ``exit`` and tear down the process."""
        if not self._connected or self._process is None:
            return

        try:
            self.send_request("shutdown", {})
            self.send_notification("exit", {})
        except Exception:  # noqa: BLE001
            logger.debug("Error during LSP shutdown sequence", exc_info=True)

        self._cleanup_process()

    def send_request(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Send a JSON-RPC **request** (expects a response).

        Returns the ``result`` field of the response, or None on
        timeout / error / not connected.
        """
        if not self._connected or self._process is None:
            return None

        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        try:
            self._write_message(message)
            response = self._read_message()
        except Exception:  # noqa: BLE001
            logger.debug("send_request(%s) failed", method, exc_info=True)
            return None

        if response is None:
            return None

        if "error" in response:
            logger.warning(
                "LSP error for %s: %s",
                method,
                response["error"],
            )
            return None

        return response.get("result")

    def send_notification(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        """Send a JSON-RPC **notification** (no ``id``, no response)."""
        if not self._connected or self._process is None:
            return

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            self._write_message(message)
        except Exception:  # noqa: BLE001
            logger.debug("send_notification(%s) failed", method, exc_info=True)

    def is_connected(self) -> bool:
        """Return True if the server process is alive and connected."""
        if not self._connected or self._process is None:
            return False
        # Poll returns None while process is still running
        return self._process.poll() is None

    @staticmethod
    def encode_message(body: dict[str, Any]) -> bytes:
        """Encode a JSON-RPC message with Content-Length header.

        Public so tests can verify framing without a live process.
        """
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        return header + payload

    def _write_message(self, body: dict[str, Any]) -> None:
        """Write a framed JSON-RPC message to the server's stdin."""
        assert self._process is not None and self._process.stdin is not None
        raw = self.encode_message(body)
        self._process.stdin.write(raw)
        self._process.stdin.flush()

    def _read_message(self) -> dict[str, Any] | None:
        """Read one framed JSON-RPC message from the server's stdout.

        Uses a background thread + join(timeout) so we never block
        indefinitely.
        """
        assert self._process is not None and self._process.stdout is not None

        result_holder: list[dict[str, Any] | None] = [None]

        def _reader() -> None:
            try:
                stdout = self._process.stdout  # type: ignore[union-attr]
                content_length = 0
                content_length = 0
                while True:
                    line = stdout.readline()
                    if not line:
                        return  # EOF
                    line_str = line.decode("ascii").strip()
                    if not line_str:
                        break
                    if line_str.startswith(_CONTENT_LENGTH_HEADER.strip()):
                        content_length = int(line_str[len(_CONTENT_LENGTH_HEADER.strip()):])

                if content_length == 0:
                    return

                data = stdout.read(content_length)
                if data:
                    result_holder[0] = json.loads(data.decode("utf-8"))
            except Exception:  # noqa: BLE001
                logger.debug("_reader failed", exc_info=True)

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)

        if thread.is_alive():
            logger.warning("LSP read timed out after %.1fs", self._timeout)
            return None

        return result_holder[0]

    def _cleanup_process(self) -> None:
        """Terminate / kill the server process and reset state."""
        self._connected = False
        self._initialized = False
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=1)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._process = None

    def __enter__(self) -> LSPClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()

    def __repr__(self) -> str:
        cmd = self._server_cmd or "(stub)"
        return f"<LSPClient cmd={cmd!r} connected={self.is_connected()}>"
