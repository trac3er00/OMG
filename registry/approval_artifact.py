"""Signed approval artifacts binding approvals to artifact digests via Ed25519/minisign."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from registry.verify_artifact import (
    _canonical_json,
    _key_id_from_public_key,
    _load_ed25519_backend,
    _load_trusted_signers,
    _parse_minisign_detached,
    _utc_now,
    sign_artifact,
)

_APPROVAL_TYPE = "omg-approval-artifact-v1"


@dataclass
class ApprovalArtifact:
    artifact_digest: str
    action: str
    scope: str
    reason: str
    signer_key_id: str
    issued_at: str
    signature: str
    run_id: str = ""


def _approval_signing_payload(approval: ApprovalArtifact) -> dict[str, object]:
    # Security-critical: signature field excluded from signing payload
    return {
        "artifact_digest": approval.artifact_digest,
        "action": approval.action,
        "scope": approval.scope,
        "reason": approval.reason,
        "signer_key_id": approval.signer_key_id,
        "issued_at": approval.issued_at,
        "type": _APPROVAL_TYPE,
        "run_id": approval.run_id,
    }


def create_approval_artifact(
    artifact_digest: str,
    action: str,
    scope: str,
    reason: str,
    signer_key_id: str,
    signer_private_key: str,
    run_id: str = "",
) -> ApprovalArtifact:

    clean_digest = str(artifact_digest).strip().lower()
    if len(clean_digest) != 64 or any(ch not in "0123456789abcdef" for ch in clean_digest):
        raise ValueError("artifact_digest_must_be_sha256_hex")
    if not str(action).strip():
        raise ValueError("action_required")
    if not str(scope).strip():
        raise ValueError("scope_required")
    if not signer_private_key:
        raise ValueError("signer_private_key_required")

    issued_at = _utc_now()

    approval = ApprovalArtifact(
        artifact_digest=clean_digest,
        action=str(action).strip(),
        scope=str(scope).strip(),
        reason=str(reason).strip(),
        signer_key_id=signer_key_id,
        issued_at=issued_at,
        signature="",
        run_id=str(run_id).strip(),
    )

    sig_result = sign_artifact(
        artifact_path=f"approval:{clean_digest}",
        subject_digest=clean_digest,
        signer_key_id=signer_key_id,
        signer_private_key=signer_private_key,
        trusted_comment=(
            f"type={_APPROVAL_TYPE} keyid={signer_key_id} "
            f"issued_at={issued_at} digest={clean_digest}"
        ),
        signing_payload=_approval_signing_payload(approval),
    )

    approval.signature = sig_result["signature"]
    return approval


def verify_approval_artifact(
    approval: ApprovalArtifact | dict[str, Any],
    expected_artifact_digest: str,
) -> dict[str, Any]:

    if isinstance(approval, ApprovalArtifact):
        data = asdict(approval)
    elif isinstance(approval, dict):
        data = dict(approval)
    else:
        return {"valid": False, "reason": "invalid approval artifact type"}

    required = ("artifact_digest", "action", "scope", "reason", "signer_key_id", "issued_at", "signature")
    for field in required:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return {"valid": False, "reason": f"missing or empty field: {field}"}
    run_id_value = data.get("run_id", "")
    if run_id_value is not None and not isinstance(run_id_value, str):
        return {"valid": False, "reason": "run_id must be a string when present"}

    clean_expected = str(expected_artifact_digest).strip().lower()
    clean_actual = str(data["artifact_digest"]).strip().lower()
    if clean_actual != clean_expected:
        return {"valid": False, "reason": "artifact digest mismatch"}

    key_id = data["signer_key_id"]
    trusted_signers = _load_trusted_signers()
    signer = trusted_signers.get(key_id)
    if signer is None:
        return {"valid": False, "reason": "unknown signer key id"}
    if str(signer.get("algorithm", "")) != "ed25519-minisign":
        return {"valid": False, "reason": "algorithm mismatch for trusted signer"}

    public_key_b64 = signer.get("public_key")
    if not isinstance(public_key_b64, str) or not public_key_b64:
        return {"valid": False, "reason": "invalid trusted signer public key"}
    try:
        _, _, Ed25519PublicKey = _load_ed25519_backend()
        public_key_raw = base64.b64decode(public_key_b64, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_raw)
    except ModuleNotFoundError as exc:
        return {"valid": False, "reason": str(exc)}
    except Exception:
        return {"valid": False, "reason": "invalid trusted signer public key"}

    if _key_id_from_public_key(public_key_raw) != key_id:
        return {"valid": False, "reason": "trusted signer key id mismatch"}

    signature_value = data["signature"]
    try:
        detached_sig, _trusted_comment, _tc_sig = _parse_minisign_detached(signature_value, None)
    except ValueError as exc:
        return {"valid": False, "reason": str(exc)}

    temp_approval = ApprovalArtifact(
        artifact_digest=clean_actual,
        action=data["action"],
        scope=data["scope"],
        reason=data["reason"],
        signer_key_id=key_id,
        issued_at=data["issued_at"],
        signature="",
        run_id=str(run_id_value).strip(),
    )
    payload = _approval_signing_payload(temp_approval)

    try:
        public_key.verify(detached_sig, _canonical_json(payload))
    except Exception:
        return {"valid": False, "reason": "invalid approval signature"}

    return {"valid": True, "reason": "verified"}


def load_approval_artifact_from_path(
    path: str | Path,
    expected_artifact_digest: str,
) -> dict[str, Any]:

    file_path = Path(path)
    if not file_path.is_file():
        return {"valid": False, "reason": f"file not found: {path}", "approval": None}

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {"valid": False, "reason": "invalid JSON in approval artifact file", "approval": None}

    if not isinstance(data, dict):
        return {"valid": False, "reason": "approval artifact must be a JSON object", "approval": None}

    result = verify_approval_artifact(data, expected_artifact_digest)
    return {
        "valid": result["valid"],
        "reason": result["reason"],
        "approval": data if result["valid"] else None,
    }


def build_tool_approval_digest(lane_name: str, tool_name: str, run_id: str) -> str:
    payload = {
        "lane": str(lane_name).strip().lower(),
        "tool": str(tool_name).strip(),
        "run_id": str(run_id).strip(),
        "type": "omg-tool-fabric-approval-v1",
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def verify_tool_approval(
    approval: ApprovalArtifact | dict[str, Any],
    *,
    lane_name: str,
    tool_name: str,
    run_id: str,
) -> dict[str, Any]:
    expected_digest = build_tool_approval_digest(lane_name=lane_name, tool_name=tool_name, run_id=run_id)
    verified = verify_approval_artifact(approval, expected_artifact_digest=expected_digest)
    if not bool(verified.get("valid")):
        return verified

    approval_obj: dict[str, Any]
    if isinstance(approval, ApprovalArtifact):
        approval_obj = asdict(approval)
    elif isinstance(approval, dict):
        approval_obj = dict(approval)
    else:
        return {"valid": False, "reason": "invalid approval artifact type"}

    run_binding = str(approval_obj.get("run_id", "")).strip()
    if not run_binding:
        scope = str(approval_obj.get("scope", "")).strip()
        token = f"/runs/{run_id}"
        if token in scope:
            run_binding = run_id
    if run_binding != str(run_id).strip():
        return {"valid": False, "reason": "approval artifact run_id mismatch"}
    return verified
