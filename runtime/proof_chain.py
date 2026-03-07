from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_evidence_pack(output_root: Path) -> tuple[str, dict[str, Any]]:
    evidence_dir = output_root / ".omg" / "evidence"
    if not evidence_dir.exists():
        return "", {}
    evidence_files = sorted(path for path in evidence_dir.glob("*.json") if path.is_file())
    evidence_payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in evidence_files:
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if payload.get("schema") == "EvidencePack":
            evidence_payloads.append((path, payload))
    if not evidence_payloads:
        return "", {}
    path, payload = evidence_payloads[-1]
    return str(path.relative_to(output_root)), payload


def assemble_proof_chain(project_dir: str, *, evidence_path: str | None = None) -> dict[str, Any]:
    output_root = Path(project_dir)

    trace_rows = _read_jsonl(output_root / ".omg" / "tracebank" / "events.jsonl")
    trace_by_id = {
        str(item.get("trace_id", "")): item
        for item in trace_rows
        if isinstance(item, dict) and item.get("trace_id")
    }

    eval_path = output_root / ".omg" / "evals" / "latest.json"
    eval_payload: dict[str, Any] = _load_json(eval_path) if eval_path.exists() else {}

    if evidence_path:
        selected_path = str(evidence_path)
        evidence_payload = _load_json(output_root / selected_path)
    else:
        selected_path, evidence_payload = _latest_evidence_pack(output_root)

    trace_id = ""
    trace_ids = evidence_payload.get("trace_ids", [])
    if isinstance(trace_ids, list) and trace_ids:
        trace_id = str(trace_ids[0])
    if not trace_id:
        trace_id = str(eval_payload.get("trace_id", ""))

    trace_payload = trace_by_id.get(trace_id, {})
    lineage = eval_payload.get("lineage") or evidence_payload.get("lineage") or {}
    eval_id = str(eval_payload.get("eval_id", ""))
    if not eval_id and trace_id:
        eval_id = f"eval-{hashlib.sha256(trace_id.encode('utf-8')).hexdigest()[:12]}"

    chain = {
        "schema": "ProofChain",
        "trace_id": trace_id,
        "eval_id": eval_id,
        "eval_trace_id": str(eval_payload.get("trace_id", "")),
        "lineage": lineage,
        "lineage_trace_id": str((lineage or {}).get("trace_id", "")) if isinstance(lineage, dict) else "",
        "evidence_path": selected_path,
        "security_scans": evidence_payload.get("security_scans", []),
        "timestamp": evidence_payload.get("timestamp") or trace_payload.get("timestamp") or eval_payload.get("timestamp") or eval_payload.get("evaluated_at") or "unknown",
        "executor": evidence_payload.get("executor") or trace_payload.get("executor") or eval_payload.get("executor") or {"user": "unknown", "pid": "unknown"},
        "environment": evidence_payload.get("environment") or trace_payload.get("environment") or eval_payload.get("environment") or {"hostname": "unknown", "platform": "unknown"},
        "ci_job_url": evidence_payload.get("ci_job_url") or "",
        "external_inputs": evidence_payload.get("external_inputs", []),
        "artifacts": {
            "trace": trace_payload.get("path", ".omg/tracebank/events.jsonl"),
            "eval": ".omg/evals/latest.json" if eval_payload else "",
            "lineage": str((lineage or {}).get("path", "")) if isinstance(lineage, dict) else "",
            "evidence": selected_path,
        },
    }
    validation = validate_proof_chain(chain)
    chain["status"] = validation["status"]
    chain["blockers"] = validation["blockers"]
    return chain


def validate_proof_chain(chain: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []

    required_fields = (
        "trace_id",
        "eval_id",
        "lineage",
        "evidence_path",
        "timestamp",
        "executor",
        "environment",
    )
    for field in required_fields:
        value = chain.get(field)
        if value in ("", None, [], {}):
            blockers.append(f"proof_chain_missing_{field}")

    trace_id = str(chain.get("trace_id", ""))
    eval_trace_id = str(chain.get("eval_trace_id", ""))
    if trace_id and eval_trace_id and trace_id != eval_trace_id:
        blockers.append("proof_chain_trace_eval_mismatch")

    evidence_path = str(chain.get("evidence_path", ""))
    if evidence_path and not evidence_path.startswith(".omg/evidence/"):
        blockers.append("proof_chain_evidence_path_outside_runtime_evidence")

    security_scans = chain.get("security_scans", [])
    if isinstance(security_scans, list):
        linked_scan = any(isinstance(scan, dict) and str(scan.get("path", "")).startswith(".omg/evidence/") for scan in security_scans)
        if not linked_scan:
            blockers.append("proof_chain_missing_security_check_link")
    else:
        blockers.append("proof_chain_missing_security_check_link")

    lineage = chain.get("lineage", {})
    if isinstance(lineage, dict):
        lineage_trace_id = str(lineage.get("trace_id", "") or chain.get("lineage_trace_id", ""))
        if trace_id and lineage_trace_id and trace_id != lineage_trace_id:
            blockers.append("proof_chain_lineage_trace_mismatch")
    else:
        blockers.append("proof_chain_invalid_lineage")

    return {
        "schema": "ProofChainValidationResult",
        "status": "ok" if not blockers else "error",
        "blockers": blockers,
    }
