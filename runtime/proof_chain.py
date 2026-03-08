from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_REQUIRED_ARTIFACT_FIELDS = ("kind", "path", "sha256", "parser", "summary", "trace_id")


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


def _hash_path(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _normalize_evidence_pack(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("evidence_pack_invalid_payload")
    schema_version = payload.get("schema_version")
    if schema_version is None:
        return payload
    if schema_version != 2:
        raise ValueError("evidence_pack_unsupported_schema_version")

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("evidence_pack_invalid_artifacts")

    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ValueError(f"evidence_pack_artifact_invalid_type:{index}")
        for field in _REQUIRED_ARTIFACT_FIELDS:
            value = str(artifact.get(field, "")).strip()
            if not value:
                raise ValueError(f"evidence_pack_artifact_missing_{field}:{index}")
    return payload


def _artifact_record(*, kind: str, path: str, parser: str, summary: str, trace_id: str, sha256: str = "") -> dict[str, str]:
    return {
        "kind": kind,
        "path": path,
        "sha256": sha256,
        "parser": parser,
        "summary": summary,
        "trace_id": trace_id,
    }


def _build_chain_artifacts(
    *,
    output_root: Path,
    selected_path: str,
    evidence_payload: dict[str, Any],
    trace_payload: dict[str, Any],
    eval_payload: dict[str, Any],
    lineage: dict[str, Any] | Any,
    trace_id: str,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    raw_artifacts = evidence_payload.get("artifacts", [])
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            artifacts.append(
                _artifact_record(
                    kind=str(item.get("kind", "")).strip() or "artifact",
                    path=path,
                    sha256=str(item.get("sha256", "")).strip(),
                    parser=str(item.get("parser", "")).strip() or "unknown",
                    summary=str(item.get("summary", "")).strip() or "evidence artifact",
                    trace_id=str(item.get("trace_id", "")).strip() or trace_id,
                )
            )

    lineage_path = str((lineage or {}).get("path", "")).strip() if isinstance(lineage, dict) else ""
    canonical_artifacts = [
        ("trace", str(trace_payload.get("path", ".omg/tracebank/events.jsonl")).strip(), "jsonl", "tracebank event stream"),
        ("eval", ".omg/evals/latest.json" if eval_payload else "", "json", "evaluation result"),
        ("lineage", lineage_path, "json", "lineage manifest"),
        ("evidence", selected_path, "json", "evidence pack"),
    ]
    for kind, path, parser, summary in canonical_artifacts:
        if not path:
            continue
        file_path = output_root / path
        artifacts.append(
            _artifact_record(
                kind=kind,
                path=path,
                sha256=_hash_path(file_path),
                parser=parser,
                summary=summary,
                trace_id=trace_id,
            )
        )
    return artifacts


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
        evidence_payload = _normalize_evidence_pack(_load_json(output_root / selected_path))
    else:
        selected_path, evidence_payload = _latest_evidence_pack(output_root)
        evidence_payload = _normalize_evidence_pack(evidence_payload)

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
        "schema_version": 2,
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
        "artifacts": _build_chain_artifacts(
            output_root=output_root,
            selected_path=selected_path,
            evidence_payload=evidence_payload,
            trace_payload=trace_payload,
            eval_payload=eval_payload,
            lineage=lineage,
            trace_id=trace_id,
        ),
    }
    validation = validate_proof_chain(chain)
    chain["status"] = validation["status"]
    chain["blockers"] = validation["blockers"]

    try:
        from runtime.background_verification import publish_verification_state

        evidence_links = [selected_path] if selected_path else []
        publish_verification_state(
            project_dir=project_dir,
            run_id=str(chain.get("eval_id", "")),
            status=str(validation["status"]),
            blockers=list(validation.get("blockers", [])),
            evidence_links=evidence_links,
            progress={"phase": "proof_chain_assembled"},
        )
    except Exception:
        pass

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


def build_proof_gate_input(project_dir: str, *, evidence_path: str | None = None) -> dict[str, Any]:
    output_root = Path(project_dir)
    chain = assemble_proof_chain(project_dir, evidence_path=evidence_path)

    eval_path = output_root / ".omg" / "evals" / "latest.json"
    eval_output = _load_json(eval_path) if eval_path.exists() else {}

    if evidence_path:
        selected_path = str(evidence_path)
        evidence_payload = _normalize_evidence_pack(_load_json(output_root / selected_path))
    else:
        selected_path, evidence_payload = _latest_evidence_pack(output_root)
        evidence_payload = _normalize_evidence_pack(evidence_payload)

    security_evidence = _resolve_security_evidence(output_root=output_root, evidence_payload=evidence_payload)
    browser_evidence = _resolve_browser_evidence(output_root=output_root, evidence_payload=evidence_payload)

    return {
        "claims": evidence_payload.get("claims", []),
        "proof_chain": chain,
        "eval_output": eval_output,
        "security_evidence": security_evidence,
        "browser_evidence": browser_evidence,
        "evidence_path": selected_path,
    }


def _resolve_security_evidence(*, output_root: Path, evidence_payload: dict[str, Any]) -> dict[str, Any]:
    scans = evidence_payload.get("security_scans", [])
    if not isinstance(scans, list):
        return {}
    for item in scans:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        evidence_path = output_root / path
        if evidence_path.exists():
            payload = _load_json(evidence_path)
            if isinstance(payload, dict):
                return payload
    return {}


def _resolve_browser_evidence(*, output_root: Path, evidence_payload: dict[str, Any]) -> dict[str, Any]:
    candidates: list[str] = []
    browser_evidence = evidence_payload.get("browser_evidence")
    if isinstance(browser_evidence, dict):
        direct_path = str(browser_evidence.get("path", "")).strip()
        if direct_path:
            candidates.append(direct_path)
        if browser_evidence.get("schema") == "BrowserEvidence":
            return browser_evidence
    browser_trace = evidence_payload.get("browser_trace")
    if isinstance(browser_trace, dict):
        path = str(browser_trace.get("evidence_path", "")).strip()
        if path:
            candidates.append(path)

    adapter_matches = sorted(output_root.glob(".omg/evidence/playwright-adapter-*.json"))
    if adapter_matches:
        candidates.append(adapter_matches[0].relative_to(output_root).as_posix())

    candidates.extend(
        [
            ".omg/evidence/browser-evidence.json",
            ".omg/evidence/browser-proof.json",
        ]
    )
    for rel in candidates:
        path = output_root / rel
        if not path.exists():
            continue
        payload = _load_json(path)
        if isinstance(payload, dict):
            return payload
    return {}
