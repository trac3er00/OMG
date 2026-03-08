from __future__ import annotations

import json
from http.server import HTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.request import Request, urlopen

from control_plane.server import _main, make_handler
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


def test_nonloopback_blocked_without_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0"]):
        rc = _main()
    assert rc == 1


def test_nonloopback_allowed_with_unsafe_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0", "--unsafe"]), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with("0.0.0.0", 8787, None)


def test_nonloopback_allowed_with_dev_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0", "--dev"]), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with("0.0.0.0", 8787, None)


def test_server_security_check_with_waivers(tmp_path) -> None:
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload = _post_json(
            f"{base}/v2/security/check",
            {"scope": ".", "waivers": ["shell-true"]},
        )
        assert v2_status == 200
        assert v2_payload["schema"] == "SecurityCheckResult"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload = _post_json(
            f"{base}/v1/security/check",
            {"scope": ".", "waivers": ["shell-true"]},
        )
        assert v1_status == 200
        assert v1_payload["deprecated"] is True
        assert v1_payload["schema"] == "SecurityCheckResult"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_server_claim_judge_v2_and_v1(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        claims = [{"claim_type": "test_pass", "subject": "auth", "artifacts": ["a.json"], "trace_ids": ["t-1"]}]

        v2_status, v2_payload = _post_json(f"{base}/v2/trust/claim-judge", {"claims": claims})
        assert v2_status == 200
        assert v2_payload["schema"] == "ClaimJudgeResults"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload = _post_json(f"{base}/v1/trust/claim-judge", {"claims": claims})
        assert v1_status == 200
        assert v1_payload["deprecated"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_server_test_intent_lock_v2_and_v1(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload = _post_json(
            f"{base}/v2/trust/test-intent-lock",
            {"action": "lock", "intent": {"tests": ["test_auth"]}},
        )
        assert v2_status == 200
        assert v2_payload["status"] == "locked"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload = _post_json(
            f"{base}/v1/trust/test-intent-lock",
            {"action": "lock", "intent": {"tests": ["test_auth"]}},
        )
        assert v1_status == 200
        assert v1_payload["deprecated"] is True
        assert v1_payload["status"] == "locked"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loopback_allowed_without_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "127.0.0.1"]), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with("127.0.0.1", 8787, None)
