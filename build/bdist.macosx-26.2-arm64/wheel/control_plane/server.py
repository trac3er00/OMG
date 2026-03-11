"""Lightweight HTTP server for OMG control-plane APIs."""
from __future__ import annotations

import argparse
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Any

from control_plane.service import ControlPlaneService


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


_POST_ROUTE_TABLE = {
    "/v2/policy/evaluate": ("policy_evaluate", False),
    "/v1/policy/evaluate": ("policy_evaluate", True),
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
    decorated = dict(payload)
    decorated["api_version"] = "v2"
    if deprecated:
        decorated["deprecated"] = True
        decorated["deprecated_alias"] = "v1"
    return decorated


def make_handler(service: ControlPlaneService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = _GET_ROUTE_TABLE.get(self.path)
            if route is not None:
                method_name, deprecated = route
                status, payload = getattr(service, method_name)()
                _json_response(self, status, _decorate_payload(payload, deprecated=deprecated))
                return
            _json_response(self, 404, {"status": "error", "message": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            payload = _read_json(self)
            route = _POST_ROUTE_TABLE.get(self.path)
            if route is not None:
                method_name, deprecated = route
                status, out = getattr(service, method_name)(payload)
                _json_response(self, status, _decorate_payload(out, deprecated=deprecated))
                return

            _json_response(self, 404, {"status": "error", "message": "Not found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Quiet default request logs; keep response JSON clean for local usage.
            return

    return Handler


def run_server(host: str = "127.0.0.1", port: int = 8787, project_dir: str | None = None) -> None:
    service = ControlPlaneService(project_dir=project_dir)
    handler = make_handler(service)
    server = HTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run OMG control-plane API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--project-dir", default=None)
    parser.add_argument(
        "--unsafe", action="store_true",
        help="Allow binding to non-loopback addresses (no auth; use at own risk)",
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="Development mode — implies --unsafe for non-loopback binding",
    )
    args = parser.parse_args()

    if args.host not in _LOOPBACK_HOSTS:
        if not (args.unsafe or args.dev):
            print(
                f"ERROR: Binding to '{args.host}' exposes the control plane to the network.\n"
                "No authentication is configured. This is blocked by default.\n"
                "Pass --unsafe or --dev to override.",
                file=sys.stderr,
            )
            return 1
        print(
            f"⚠ WARNING: Binding to {args.host} with {'--unsafe' if args.unsafe else '--dev'} flag. "
            "No authentication is configured.",
            file=sys.stderr,
        )

    run_server(args.host, args.port, args.project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
