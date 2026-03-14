"""Local-only authenticated supervisor sessions."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.exec_kernel import get_exec_kernel
from runtime.release_run_coordinator import resolve_current_run_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def issue_local_supervisor_session(
    project_dir: str,
    *,
    worker_id: str,
    shared_secret: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    resolved_run_id = run_id or resolve_current_run_id(project_dir)
    session_id = f"session-{uuid4().hex}"
    issued_at = _now()
    token_payload = {
        "session_id": session_id,
        "worker_id": worker_id,
        "issued_at": issued_at,
        "run_id": resolved_run_id,
    }
    payload_json = json.dumps(token_payload, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(shared_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(
        json.dumps({"payload": token_payload, "signature": signature}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    result = {
        "schema": "RemoteSupervisorSession",
        "status": "ok",
        "session_id": session_id,
        "worker_id": worker_id,
        "issued_at": issued_at,
        "run_id": resolved_run_id,
        "local_only": True,
        "token": token,
    }

    rel_path = Path(".omg") / "supervisor" / "sessions" / f"{session_id}.json"
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in result.items() if k != "token"}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    result["path"] = rel_path.as_posix()
    if resolved_run_id:
        get_exec_kernel(project_dir).record_supervisor_session(resolved_run_id, result)
    return result


def verify_local_supervisor_token(token: str, *, shared_secret: str) -> dict[str, Any]:
    decoded = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    payload = decoded["payload"]
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = str(decoded["signature"])
    expected = hmac.new(shared_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
    status = "ok" if hmac.compare_digest(signature, expected) else "error"
    return {
        "schema": "RemoteSupervisorTokenVerification",
        "status": status,
        "session_id": str(payload["session_id"]),
        "worker_id": str(payload["worker_id"]),
        "issued_at": str(payload["issued_at"]),
        "run_id": str(payload.get("run_id") or ""),
        "local_only": True,
    }
