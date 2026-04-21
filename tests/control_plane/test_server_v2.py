from __future__ import annotations

import json
from http.server import HTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control_plane.server import _main, ControlPlaneBindingError, make_handler, run_server
from control_plane.service import ControlPlaneService



def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), dict(response.headers.items())
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body), dict(exc.headers.items())



def _post_raw(
    url: str,
    raw_body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = Request(url, data=raw_body, headers=request_headers, method="POST")
    try:
        with urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), dict(response.headers.items())
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body), dict(exc.headers.items())



def test_server_supports_v2_endpoints_and_v1_aliases(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload, headers = _post_json(
            f"{base}/v2/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
        )
        v1_status, v1_payload, _ = _post_json(
            f"{base}/v1/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
        )

        assert v2_status == 200
        assert v2_payload["action"] == "deny"
        assert v2_payload["api_version"] == "v2"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert v1_status == 200
        assert v1_payload["action"] == "deny"
        assert v1_payload["deprecated"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_server_rejects_malformed_json_with_security_headers(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload, headers = _post_raw(
            f"{base}/v2/policy/evaluate",
            b'{"tool":',
        )
        assert status == 400
        assert payload["message"] == "Malformed JSON body"
        assert headers["X-Frame-Options"] == "DENY"
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_server_supports_vision_job_endpoints_and_aliases(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload, _ = _post_json(
            f"{base}/v2/vision/jobs",
            {"mode": "compare", "inputs": ["left.png", "right.png"]},
        )
        assert v2_status == 400
        assert v2_payload["error_code"] == "INVALID_VISION_INPUT"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload, _ = _post_json(
            f"{base}/v1/vision/jobs",
            {"mode": "compare", "inputs": ["left.png", "right.png"]},
        )
        assert v1_status == 400
        assert v1_payload["deprecated"] is True
        assert v1_payload["error_code"] == "INVALID_VISION_INPUT"
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_handler_requires_bearer_token_when_configured(tmp_path) -> None:
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service, auth_token="secret-token"))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        missing_status, missing_payload, _ = _post_json(
            f"{base}/v2/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
        )
        assert missing_status == 401
        assert missing_payload["message"] == "Missing bearer token"

        invalid_status, invalid_payload, _ = _post_json(
            f"{base}/v2/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert invalid_status == 401
        assert invalid_payload["message"] == "Invalid bearer token"

        ok_status, ok_payload, _ = _post_json(
            f"{base}/v2/policy/evaluate",
            {"tool": "Bash", "input": {"command": "rm -rf /"}},
            headers={"Authorization": "Bearer secret-token"},
        )
        assert ok_status == 200
        assert ok_payload["action"] == "deny"
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_nonloopback_blocked_without_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0"]):
        rc = _main()
    assert rc == 1



def test_nonloopback_blocked_without_auth_token_even_with_unsafe_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0", "--unsafe"]):
        rc = _main()
    assert rc == 1



def test_nonloopback_allowed_with_unsafe_flag_and_auth_token() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0", "--unsafe", "--auth-token", "secret-token"]), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with(
        "0.0.0.0",
        8787,
        None,
        auth_token="secret-token",
        allow_non_loopback=True,
    )



def test_nonloopback_allowed_with_dev_flag_and_env_auth_token() -> None:
    with patch("sys.argv", ["server.py", "--host", "0.0.0.0", "--dev"]), \
         patch.dict("os.environ", {"OMG_CONTROL_TOKEN": "env-secret"}, clear=False), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with(
        "0.0.0.0",
        8787,
        None,
        auth_token="env-secret",
        allow_non_loopback=True,
    )



def test_server_security_check_with_waivers(tmp_path) -> None:
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload, _ = _post_json(
            f"{base}/v2/security/check",
            {"scope": ".", "waivers": ["shell-true"]},
        )
        assert v2_status == 200
        assert v2_payload["schema"] == "SecurityCheckResult"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload, _ = _post_json(
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

        v2_status, v2_payload, _ = _post_json(f"{base}/v2/trust/claim-judge", {"claims": claims})
        assert v2_status == 200
        assert v2_payload["schema"] == "ClaimJudgeResults"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload, _ = _post_json(f"{base}/v1/trust/claim-judge", {"claims": claims})
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

        v2_status, v2_payload, _ = _post_json(
            f"{base}/v2/trust/test-intent-lock",
            {"action": "lock", "intent": {"tests": ["test_auth"]}},
        )
        assert v2_status == 200
        assert v2_payload["status"] == "locked"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload, _ = _post_json(
            f"{base}/v1/trust/test-intent-lock",
            {"action": "lock", "intent": {"tests": ["test_auth"]}},
        )
        assert v1_status == 200
        assert v1_payload["deprecated"] is True
        assert v1_payload["status"] == "locked"
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_mutation_gate_endpoint_v2_blocks_no_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload, _ = _post_json(
            f"{base}/v2/trust/mutation-gate",
            {"tool": "Write", "file_path": "foo.py", "project_dir": str(tmp_path), "lock_id": None},
        )
        assert v2_status == 200
        assert v2_payload["status"] == "blocked"
        assert v2_payload["reason"] == "mutation_context_required"
        assert v2_payload["api_version"] == "v2"

        v1_status, v1_payload, _ = _post_json(
            f"{base}/v1/trust/mutation-gate",
            {"tool": "Write", "file_path": "foo.py", "project_dir": str(tmp_path), "lock_id": None},
        )
        assert v1_status == 200
        assert v1_payload["status"] == "blocked"
        assert v1_payload["deprecated"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_mutation_gate_endpoint_v2_blocks_strict_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)
    service = ControlPlaneService(project_dir=str(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        v2_status, v2_payload, _ = _post_json(
            f"{base}/v2/trust/mutation-gate",
            {"tool": "Write", "file_path": "bar.py", "project_dir": str(tmp_path), "lock_id": None},
        )
        assert v2_status == 200
        assert v2_payload["status"] == "blocked"
        assert v2_payload["reason"] == "mutation_context_required"
        assert v2_payload["api_version"] == "v2"
    finally:
        server.shutdown()
        thread.join(timeout=5)



def test_run_server_blocks_programmatic_nonloopback_without_override() -> None:
    try:
        run_server("0.0.0.0", 8787, None)
    except ControlPlaneBindingError as exc:
        assert "exposes the control plane to the network" in str(exc)
    else:
        raise AssertionError("Expected ControlPlaneBindingError")



def test_run_server_requires_auth_when_programmatic_nonloopback_is_explicitly_allowed() -> None:
    try:
        run_server("0.0.0.0", 8787, None, allow_non_loopback=True)
    except ControlPlaneBindingError as exc:
        assert "requires an HTTP bearer token" in str(exc)
    else:
        raise AssertionError("Expected ControlPlaneBindingError")



def test_loopback_allowed_without_flag() -> None:
    with patch("sys.argv", ["server.py", "--host", "127.0.0.1"]), \
         patch("control_plane.server.run_server") as mock_run:
        rc = _main()
    assert rc == 0
    mock_run.assert_called_once_with(
        "127.0.0.1",
        8787,
        None,
        auth_token=None,
        allow_non_loopback=False,
    )
