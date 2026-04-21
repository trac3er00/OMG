"""Lightweight HTTP server for OMG control-plane APIs."""

from __future__ import annotations

import argparse
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from typing import Any

from control_plane.service import ControlPlaneService


_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _json_response(
    handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]
) -> None:
    """Send a JSON response to the client.

    Args:
        handler: The HTTP request handler.
        status: HTTP status code.
        payload: Dictionary to be sent as JSON.
    """
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for header, value in _SECURITY_HEADERS.items():
        handler.send_header(header, value)
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    """Read and parse JSON from the request body.

    Args:
        handler: The HTTP request handler.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If the request body is not a JSON object.
    """
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed JSON body") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


_POST_ROUTE_TABLE = {
    "/v2/policy/evaluate": ("policy_evaluate", False),
    "/v1/policy/evaluate": ("policy_evaluate", True),
    "/v2/vision/jobs": ("vision_jobs", False),
    "/v1/vision/jobs": ("vision_jobs", True),
    "/v2/trust/review": ("trust_review", False),
    "/v1/trust/review": ("trust_review", True),
    "/v2/evidence/ingest": ("evidence_ingest", False),
    "/v1/evidence/ingest": ("evidence_ingest", True),
    "/v2/security/check": ("security_check", False),
    "/v1/security/check": ("security_check", True),
    "/v2/guide/assert": ("guide_assert", False),
    "/v1/guide/assert": ("guide_assert", True),
    "/v2/runtime/dispatch": ("runtime_dispatch", False),
    "/v1/runtime/dispatch": ("runtime_dispatch", True),
    "/v2/registry/verify": ("registry_verify", False),
    "/v1/registry/verify": ("registry_verify", True),
    "/v2/lab/jobs": ("lab_jobs", False),
    "/v1/lab/jobs": ("lab_jobs", True),
    "/v2/trust/claim-judge": ("claim_judge", False),
    "/v1/trust/claim-judge": ("claim_judge", True),
    "/v2/trust/test-intent-lock": ("test_intent_lock", False),
    "/v1/trust/test-intent-lock": ("test_intent_lock", True),
    "/v2/trust/mutation-gate": ("mutation_gate_check", False),
    "/v1/trust/mutation-gate": ("mutation_gate_check", True),
}

_GET_ROUTE_TABLE = {
    "/v2/scoreboard/baseline": ("scoreboard_baseline", False),
    "/v1/scoreboard/baseline": ("scoreboard_baseline", True),
}


def _decorate_payload(payload: dict[str, Any], *, deprecated: bool) -> dict[str, Any]:
    """Add metadata to the response payload.

    Args:
        payload: The original response payload.
        deprecated: Whether the endpoint is deprecated.

    Returns:
        Decorated payload with API version and optional deprecation info.
    """
    decorated = dict(payload)
    decorated["api_version"] = "v2"
    if deprecated:
        decorated["deprecated"] = True
        decorated["deprecated_alias"] = "v1"
    return decorated


def make_handler(service: ControlPlaneService, *, auth_token: str | None = None):
    """Create a request handler class bound to a service instance.

    Args:
        service: The control plane service instance.
        auth_token: Optional bearer token required on routed requests.

    Returns:
        A BaseHTTPRequestHandler subclass.
    """

    class Handler(BaseHTTPRequestHandler):
        def _require_auth(self) -> bool:
            if not auth_token:
                return True
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                _json_response(
                    self, 401, {"status": "error", "message": "Missing bearer token"}
                )
                return False
            token = header.removeprefix("Bearer ").strip()
            if not token or not compare_digest(token, auth_token):
                _json_response(
                    self, 401, {"status": "error", "message": "Invalid bearer token"}
                )
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            """Handle GET requests by routing to the appropriate service method."""
            route = _GET_ROUTE_TABLE.get(self.path)
            if route is not None:
                if not self._require_auth():
                    return
                method_name, deprecated = route
                status, payload = getattr(service, method_name)()
                _json_response(
                    self, status, _decorate_payload(payload, deprecated=deprecated)
                )
                return
            _json_response(self, 404, {"status": "error", "message": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            """Handle POST requests by reading JSON and routing to the service."""
            route = _POST_ROUTE_TABLE.get(self.path)
            if route is not None:
                if not self._require_auth():
                    return
                try:
                    payload = _read_json(self)
                except ValueError as exc:
                    _json_response(self, 400, {"status": "error", "message": str(exc)})
                    return
                method_name, deprecated = route
                status, out = getattr(service, method_name)(payload)
                _json_response(
                    self, status, _decorate_payload(out, deprecated=deprecated)
                )
                return

            _json_response(self, 404, {"status": "error", "message": "Not found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            """Override to suppress default request logging."""
            return

    return Handler


def run_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    project_dir: str | None = None,
    auth_token: str | None = None,
    *,
    allow_non_loopback: bool | None = None,
) -> None:
    """Run the HTTP server.

    Args:
        host: Host address to bind to.
        port: Port number to listen on.
        project_dir: Optional project directory for the service.
        auth_token: Optional bearer token required on routed requests.
        allow_non_loopback: Whether non-loopback binding is explicitly allowed.
    """
    _validate_binding(
        host,
        auth_token,
        allow_non_loopback=host in _LOOPBACK_HOSTS
        if allow_non_loopback is None
        else allow_non_loopback,
    )
    service = ControlPlaneService(project_dir=project_dir)
    handler = make_handler(service, auth_token=auth_token)
    server = HTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ControlPlaneBindingError(ValueError):
    """Raised when an HTTP control-plane binding violates safety requirements."""


def _validate_binding(
    host: str, auth_token: str | None, *, allow_non_loopback: bool
) -> None:
    if host in _LOOPBACK_HOSTS:
        return
    if not allow_non_loopback:
        raise ControlPlaneBindingError(
            f"Binding to '{host}' exposes the control plane to the network. "
            "Pass --unsafe/--dev in the CLI before using a non-loopback address.",
        )
    if not auth_token:
        raise ControlPlaneBindingError(
            f"Binding to '{host}' requires an HTTP bearer token. "
            "Pass --auth-token or set OMG_CONTROL_TOKEN before using a non-loopback address.",
        )


def _main() -> int:
    """Main entry point for the server CLI.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(description="Run OMG control-plane API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--project-dir", default=None)
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="Allow binding to non-loopback addresses when an auth token is configured",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Development mode — implies --unsafe for non-loopback binding",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Bearer token required for HTTP API requests. Can also be set via OMG_CONTROL_TOKEN.",
    )
    args = parser.parse_args()
    auth_token = (
        args.auth_token or os.environ.get("OMG_CONTROL_TOKEN") or ""
    ).strip() or None

    try:
        _validate_binding(
            args.host, auth_token, allow_non_loopback=bool(args.unsafe or args.dev)
        )
    except ControlPlaneBindingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.host not in _LOOPBACK_HOSTS:
        print(
            f"⚠ WARNING: Binding to {args.host} with {'--unsafe' if args.unsafe else '--dev'} flag. "
            "HTTP API access now requires a bearer token.",
            file=sys.stderr,
        )

    run_server(
        args.host,
        args.port,
        args.project_dir,
        auth_token=auth_token,
        allow_non_loopback=bool(args.unsafe or args.dev),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
