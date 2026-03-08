from __future__ import annotations

from typing import Any


def evaluate_proof_gate(input: dict[str, Any]) -> dict[str, Any]:
    claims = _as_claims(input.get("claims"))
    proof_chain = _as_dict(input.get("proof_chain"))
    eval_output = _as_dict(input.get("eval_output"))
    security_evidence = _as_dict(input.get("security_evidence"))
    browser_evidence = _as_dict(input.get("browser_evidence"))

    blockers: list[str] = []
    if not claims:
        blockers.append("proof_gate_missing_claims")

    proof_status = str(proof_chain.get("status", "error"))
    proof_blockers = proof_chain.get("blockers", [])
    if proof_status == "error":
        blockers.append("proof_gate_proof_chain_error")
    if isinstance(proof_blockers, list) and proof_blockers:
        blockers.extend(f"proof_gate_proof_chain: {item}" for item in proof_blockers)
    elif proof_blockers not in ({}, None, []):
        blockers.append("proof_gate_proof_chain_blockers_invalid")

    trace_id = str(proof_chain.get("trace_id", "")).strip()
    blockers.extend(_validate_claim_artifacts(claims))
    blockers.extend(_validate_trace_linkage(claims=claims, trace_id=trace_id, eval_output=eval_output, browser_evidence=browser_evidence))
    blockers.extend(_validate_security_and_browser_artifacts(claims=claims, security_evidence=security_evidence, browser_evidence=browser_evidence))

    unique_blockers = list(dict.fromkeys(item for item in blockers if str(item).strip()))
    evidence_summary = {
        "claim_count": len(claims),
        "proof_chain_status": proof_status,
        "proof_chain_blocker_count": len(proof_blockers) if isinstance(proof_blockers, list) else 0,
        "required_artifacts": ["junit", "coverage", "sarif", "browser_trace"],
        "trace_id": trace_id,
        "eval_trace_id": str(eval_output.get("trace_id", "")).strip(),
        "has_security_evidence": bool(security_evidence),
        "has_browser_evidence": bool(browser_evidence),
    }
    return {
        "schema": "ProofGateResult",
        "verdict": "pass" if not unique_blockers else "fail",
        "blockers": unique_blockers,
        "evidence_summary": evidence_summary,
    }


def _as_claims(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    claims: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claims.append(item)
    return claims


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _collect_artifacts(claim: dict[str, Any]) -> list[str]:
    evidence = _as_dict(claim.get("evidence"))
    raw_artifacts = evidence.get("artifacts", claim.get("artifacts", []))
    if not isinstance(raw_artifacts, list):
        return []
    artifacts: list[str] = []
    for item in raw_artifacts:
        if isinstance(item, str):
            value = item.strip().lower()
            if value:
                artifacts.append(value)
        elif isinstance(item, dict):
            for key in ("kind", "schema", "type", "path", "id"):
                value = str(item.get(key, "")).strip().lower()
                if value:
                    artifacts.append(value)
    return artifacts


def _collect_trace_ids(claim: dict[str, Any]) -> set[str]:
    evidence = _as_dict(claim.get("evidence"))
    raw_trace_ids = evidence.get("trace_ids", claim.get("trace_ids", []))
    if not isinstance(raw_trace_ids, list):
        return set()
    return {str(item).strip() for item in raw_trace_ids if str(item).strip()}


def _validate_claim_artifacts(claims: list[dict[str, Any]]) -> list[str]:
    all_artifacts: list[str] = []
    for claim in claims:
        all_artifacts.extend(_collect_artifacts(claim))

    blockers: list[str] = []
    required_tokens = {
        "junit": ("junit", "junit.xml", "surefire"),
        "coverage": ("coverage", "lcov", "coverage.xml"),
        "sarif": ("sarif", ".sarif"),
        "browser_trace": ("trace.zip", "browser_trace", "playwright", "browser-evidence"),
    }
    for key, tokens in required_tokens.items():
        if not any(any(token in artifact for token in tokens) for artifact in all_artifacts):
            blockers.append(f"proof_gate_missing_artifact_{key}")
    return blockers


def _validate_trace_linkage(
    *,
    claims: list[dict[str, Any]],
    trace_id: str,
    eval_output: dict[str, Any],
    browser_evidence: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    claim_trace_ids: set[str] = set()
    for claim in claims:
        claim_trace_ids.update(_collect_trace_ids(claim))

    if not claim_trace_ids:
        blockers.append("proof_gate_missing_tracebank_ids")
    if trace_id and claim_trace_ids and trace_id not in claim_trace_ids:
        blockers.append("proof_gate_trace_id_not_linked_in_claims")

    eval_trace_id = str(eval_output.get("trace_id", "")).strip()
    if trace_id and eval_trace_id and trace_id != eval_trace_id:
        blockers.append("proof_gate_eval_trace_mismatch")

    browser_metadata = _as_dict(browser_evidence.get("metadata"))
    browser_trace_id = str(browser_metadata.get("trace_id", browser_evidence.get("trace_id", ""))).strip()
    if browser_trace_id and trace_id and browser_trace_id != trace_id:
        blockers.append("proof_gate_browser_trace_mismatch")
    return blockers


def _validate_security_and_browser_artifacts(
    *,
    claims: list[dict[str, Any]],
    security_evidence: dict[str, Any],
    browser_evidence: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    all_artifacts: list[str] = []
    for claim in claims:
        all_artifacts.extend(_collect_artifacts(claim))

    if security_evidence:
        evidence = _as_dict(security_evidence.get("evidence"))
        sarif_path = str(evidence.get("sarif_path", "")).strip().lower()
        if sarif_path and not any("sarif" in artifact for artifact in all_artifacts):
            blockers.append("proof_gate_sarif_not_linked_by_claims")

    if browser_evidence:
        artifacts = _as_dict(browser_evidence.get("artifacts"))
        trace_path = str(artifacts.get("trace", "")).strip().lower()
        if trace_path and not any("trace" in artifact or "playwright" in artifact for artifact in all_artifacts):
            blockers.append("proof_gate_browser_trace_not_linked_by_claims")

    return blockers
