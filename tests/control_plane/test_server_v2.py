from __future__ import annotations

import json
from http.server import HTTPServer
from threading import Thread
from urllib.request import Request, urlopen

from control_plane.server import make_handler
from control_plane.service import ControlPlaneService


def _post_json(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def test_server_supports_v2_endpoints_and_v1_aliases(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload = _post_json(
            f"{base}/v2/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
        )
        v1_status, v1_payload = _post_json(
            f"{base}/v1/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
        )

        assert v2_status == 200
        assert v2_payload["action"] == "deny"
        assert v2_payload["api_version"] == "v2"
        assert v1_status == 200
        assert v1_payload["action"] == "deny"
        assert v1_payload["deprecated"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)
