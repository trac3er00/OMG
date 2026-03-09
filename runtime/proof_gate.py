from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from runtime import artifact_parsers
from runtime.evidence_requirements import FULL_REQUIREMENTS, requirements_for_profile


_REQUIRED_ARTIFACT_FIELDS = ("kind", "path", "sha256", "parser", "summary", "trace_id")

_REQUIRED_ARTIFACT_TOKENS: dict[str, tuple[str, ...]] = {
    "junit": ("junit", "junit.xml", "surefire"),
    "coverage": ("coverage", "lcov", "coverage.xml"),
    "sarif": ("sarif", ".sarif"),
    "browser_trace": ("trace.zip", "browser_trace", "playwright", "browser-evidence"),
}


def evaluate_proof_gate(input: dict[str, Any]) -> dict[str, Any]:
    claims = _as_claims(input.get("claims"))
    proof_chain = _as_dict(input.get("proof_chain"))
    eval_output = _as_dict(input.get("eval_output"))
    security_evidence = _as_dict(input.get("security_evidence"))
    browser_evidence = _as_dict(input.get("browser_evidence"))
    evidence_pack = _as_dict(input.get("evidence_pack"))
    evidence_profile = _resolve_evidence_profile(input=input, evidence_pack=evidence_pack)
    evidence_requirements = requirements_for_profile(evidence_profile)
    test_intent_lock = _as_dict(input.get("test_intent_lock"))
    test_delta = _as_dict(input.get("test_delta"))

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
    blockers.extend(_validate_claim_artifacts(claims, evidence_requirements=evidence_requirements))
    blockers.extend(_validate_trace_linkage(claims=claims, trace_id=trace_id, eval_output=eval_output, browser_evidence=browser_evidence))
    blockers.extend(_validate_security_and_browser_artifacts(claims=claims, security_evidence=security_evidence, browser_evidence=browser_evidence))
    blockers.extend(_validate_evidence_pack(evidence_pack))

    strict_mode = os.environ.get("OMG_PROOF_CHAIN_STRICT", "0").strip() == "1"
    causal_chain_blockers = _validate_lock_delta_chain(
        claims=claims,
        test_intent_lock=test_intent_lock,
        test_delta=test_delta,
        evidence_pack=evidence_pack,
    )
    if strict_mode:
        blockers.extend(causal_chain_blockers)

    unique_blockers = list(dict.fromkeys(item for item in blockers if str(item).strip()))
    advisories = [] if strict_mode else causal_chain_blockers
    evidence_summary = {
        "claim_count": len(claims),
        "proof_chain_status": proof_status,
        "proof_chain_blocker_count": len(proof_blockers) if isinstance(proof_blockers, list) else 0,
        "required_artifacts": _required_artifact_keys(evidence_requirements),
        "evidence_profile": evidence_profile,
        "evidence_requirements": list(evidence_requirements),
        "trace_id": trace_id,
        "eval_trace_id": str(eval_output.get("trace_id", "")).strip(),
        "has_security_evidence": bool(security_evidence),
        "has_browser_evidence": bool(browser_evidence),
        "has_lock_evidence": _has_lock_evidence(claims, test_intent_lock, evidence_pack),
        "has_waiver_artifact": _has_waiver_artifact(test_delta or _as_dict(evidence_pack.get("test_delta"))),
        "advisories": advisories,
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


def _validate_claim_artifacts(
    claims: list[dict[str, Any]],
    *,
    evidence_requirements: list[str],
) -> list[str]:
    all_artifacts: list[str] = []
    artifact_records: list[dict[str, Any]] = []
    for claim in claims:
        all_artifacts.extend(_collect_artifacts(claim))
        artifact_records.extend(_extract_artifact_records(claim))

    blockers: list[str] = []
    required_tokens = {
        key: _REQUIRED_ARTIFACT_TOKENS[key]
        for key in _required_artifact_keys(evidence_requirements)
        if key in _REQUIRED_ARTIFACT_TOKENS
    }
    for key, tokens in required_tokens.items():
        if not any(any(token in artifact for token in tokens) for artifact in all_artifacts):
            blockers.append(f"proof_gate_missing_artifact_{key}")

    for artifact in artifact_records:
        kind = str(artifact.get("kind", "")).strip().lower()
        path = str(artifact.get("path", "")).strip()
        if not kind or not path:
            continue

        parse_result = _parse_artifact(kind=kind, path=path)
        if not parse_result.get("valid"):
            error = str(parse_result.get("error", "")).strip()
            if error == "file_not_found":
                blockers.append(f"proof_gate_artifact_file_missing_{kind}")
            else:
                blockers.append(f"proof_gate_artifact_parse_failed_{kind}")

        hash_blocker = _validate_artifact_hash(artifact)
        if hash_blocker:
            blockers.append(hash_blocker)
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


def _validate_evidence_pack(payload: dict[str, Any]) -> list[str]:
    if not payload:
        return []
    if str(payload.get("schema", "")).strip() != "EvidencePack":
        return ["proof_gate_invalid_evidence_pack"]

    schema_version = payload.get("schema_version")
    if schema_version is None:
        return []
    if schema_version != 2:
        return ["proof_gate_unsupported_evidence_schema_version"]

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        return ["proof_gate_invalid_evidence_pack"]

    blockers: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            blockers.append("proof_gate_invalid_evidence_pack")
            continue
        for field in _REQUIRED_ARTIFACT_FIELDS:
            value = str(artifact.get(field, "")).strip()
            if not value:
                blockers.append(f"proof_gate_evidence_artifact_missing_{field}")
    return blockers


def _extract_artifact_records(claim: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = _as_dict(claim.get("evidence"))
    raw_artifacts = evidence.get("artifacts", claim.get("artifacts", []))
    if not isinstance(raw_artifacts, list):
        return []
    return [item for item in raw_artifacts if isinstance(item, dict)]


def _parse_artifact(*, kind: str, path: str) -> dict[str, Any]:
    parser = _PARSERS.get(kind)
    if parser is None:
        return {"valid": False, "summary": {}, "error": "unsupported_artifact_kind"}
    return parser(path)


def _validate_artifact_hash(artifact: dict[str, Any]) -> str | None:
    sha256_value = str(artifact.get("sha256", "")).strip().lower()
    path = str(artifact.get("path", "")).strip()
    kind = str(artifact.get("kind", "artifact")).strip().lower() or "artifact"
    if not sha256_value or not path:
        return None
    if len(sha256_value) != 64 or any(ch not in "0123456789abcdef" for ch in sha256_value):
        return None

    file_path = Path(path)
    if not file_path.exists():
        return f"proof_gate_artifact_file_missing_{kind}"
    try:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError:
        return f"proof_gate_artifact_hash_unreadable_{kind}"
    if digest != sha256_value:
        return f"proof_gate_artifact_hash_mismatch_{kind}"
    return None


def _has_lock_evidence(claims: list[dict[str, Any]], test_intent_lock: dict[str, Any], evidence_pack: dict[str, Any]) -> bool:
    lock_status = str(test_intent_lock.get("status", "")).strip().lower()
    if lock_status == "ok":
        return True
    if str(test_intent_lock.get("lock_id", "")).strip():
        return True

    test_delta = _as_dict(evidence_pack.get("test_delta"))
    if str(test_delta.get("lock_id", "")).strip():
        return True

    for claim in claims:
        if str(claim.get("lock_id", "")).strip():
            return True
        lock_verification = _as_dict(claim.get("lock_verification"))
        if str(lock_verification.get("status", "")).strip().lower() == "ok":
            return True
    return False


def _has_waiver_artifact(delta_summary: dict[str, Any]) -> bool:
    waiver = delta_summary.get("waiver_artifact")
    if isinstance(waiver, dict):
        for field in ("artifact_path", "path", "id", "reason"):
            if str(waiver.get(field, "")).strip():
                return True
    return bool(str(delta_summary.get("waiver_artifact_path", "")).strip())


def _is_weakened_or_drift_delta(delta_summary: dict[str, Any]) -> bool:
    flags = delta_summary.get("flags")
    if not isinstance(flags, list):
        return False
    risk_flags = {
        "weakened_assertions",
        "tests_mismatch",
        "selector_drift",
        "removed_touched_area_coverage",
        "integration_to_mock_downgrade",
        "snapshot_only_refresh",
    }
    normalized_flags = {str(item).strip().lower() for item in flags if str(item).strip()}
    return bool(normalized_flags & risk_flags)


def _validate_lock_delta_chain(
    *,
    claims: list[dict[str, Any]],
    test_intent_lock: dict[str, Any],
    test_delta: dict[str, Any],
    evidence_pack: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not _has_lock_evidence(claims, test_intent_lock, evidence_pack):
        blockers.append("proof_gate_missing_lock_evidence")

    delta_summary = test_delta if test_delta else _as_dict(evidence_pack.get("test_delta"))
    if _is_weakened_or_drift_delta(delta_summary) and not _has_waiver_artifact(delta_summary):
        blockers.append("proof_gate_missing_waiver_artifact")
    return blockers


def _resolve_evidence_profile(*, input: dict[str, Any], evidence_pack: dict[str, Any]) -> str:
    profile = str(input.get("evidence_profile", "")).strip()
    if profile:
        return profile
    return str(evidence_pack.get("evidence_profile", "")).strip()


def _required_artifact_keys(evidence_requirements: list[str]) -> list[str]:
    required: list[str] = []
    requirement_set = {str(item).strip() for item in evidence_requirements if str(item).strip()}
    if "tests" in requirement_set:
        required.append("junit")
    if "build" in requirement_set:
        required.append("coverage")
    if "security_scan" in requirement_set:
        required.append("sarif")
    if requirement_set == set(FULL_REQUIREMENTS):
        required.append("browser_trace")
    return required


_PARSERS: dict[str, Any] = {
    "junit": artifact_parsers.parse_junit,
    "sarif": artifact_parsers.parse_sarif,
    "coverage": artifact_parsers.parse_coverage,
    "browser_trace": artifact_parsers.parse_browser_trace,
    "diff_hunk": artifact_parsers.parse_diff_hunk,
}
