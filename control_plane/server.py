"""Lightweight HTTP server for OAL control-plane APIs."""
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


def make_handler(service: ControlPlaneService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/scoreboard/baseline":
                status, payload = service.scoreboard_baseline()
                _json_response(self, status, payload)
                return
            _json_response(self, 404, {"status": "error", "message": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            payload = _read_json(self)

            if self.path == "/v1/policy/evaluate":
                status, out = service.policy_evaluate(payload)
                _json_response(self, status, out)
                return
            if self.path == "/v1/trust/review":
                status, out = service.trust_review(payload)
                _json_response(self, status, out)
                return
            if self.path == "/v1/evidence/ingest":
                status, out = service.evidence_ingest(payload)
                _json_response(self, status, out)
                return
            if self.path == "/v1/runtime/dispatch":
                status, out = service.runtime_dispatch(payload)
                _json_response(self, status, out)
                return
            if self.path == "/v1/registry/verify":
                status, out = service.registry_verify(payload)
                _json_response(self, status, out)
                return
            if self.path == "/v1/lab/jobs":
                status, out = service.lab_jobs(payload)
                _json_response(self, status, out)
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


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run OAL control-plane API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        print(f"⚠ WARNING: Binding to {args.host} exposes the control plane to the network. No authentication is configured.", file=sys.stderr)

    run_server(args.host, args.port, args.project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

