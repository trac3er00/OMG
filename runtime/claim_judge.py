from __future__ import annotations

from typing import Any


def judge_claim(claim: dict[str, Any]) -> dict[str, Any]:
    normalized_claim = _normalize_claim(claim)
    claim_type = str(normalized_claim.get("claim_type", "")).strip()
    subject = str(normalized_claim.get("subject", "")).strip()
    artifacts = _as_non_empty_str_list(normalized_claim.get("artifacts"))
    trace_ids = _as_non_empty_str_list(normalized_claim.get("trace_ids"))
    security_scans = normalized_claim.get("security_scans")
    browser_evidence = normalized_claim.get("browser_evidence")

    reasons: list[dict[str, Any]] = []

    if not artifacts:
        reasons.append(
            {
                "code": "missing_artifacts",
                "message": "Claim must include at least one evidence artifact reference.",
                "field": "artifacts",
            }
        )

    if not trace_ids:
        reasons.append(
            {
                "code": "missing_trace_ids",
                "message": "Claim must include at least one trace identifier.",
                "field": "trace_ids",
            }
        )

    if _has_failed_scan(security_scans):
        reasons.append(
            {
                "code": "security_scan_failed",
                "message": "Security scans report unresolved failures; claim is blocked.",
                "field": "security_scans",
            }
        )

    if _has_failed_scan(browser_evidence):
        reasons.append(
            {
                "code": "browser_evidence_failed",
                "message": "Browser evidence reports failed checks; claim is blocked.",
                "field": "browser_evidence",
            }
        )

    hard_fail_codes = {"missing_artifacts", "missing_trace_ids"}
    if any(reason.get("code") in hard_fail_codes for reason in reasons):
        verdict = "fail"
    elif reasons:
        verdict = "block"
    else:
        verdict = "pass"

    return {
        "schema": "ClaimJudgeResult",
        "verdict": verdict,
        "reasons": reasons,
        "claim_type": claim_type,
        "subject": subject,
        "evidence": {
            "artifacts": artifacts,
            "trace_ids": trace_ids,
            "lineage": normalized_claim.get("lineage") if isinstance(normalized_claim.get("lineage"), dict) else {},
            "security_scans": security_scans if isinstance(security_scans, list) else [],
            "browser_evidence": browser_evidence if isinstance(browser_evidence, list) else [],
        },
    }


def _normalize_claim(claim: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_dict(claim.get("evidence"))
    artifact_refs = _as_non_empty_str_list(claim.get("artifacts"))
    artifact_refs.extend(_normalize_artifact_records(evidence.get("artifacts")))

    trace_ids = _as_non_empty_str_list(evidence.get("trace_ids"))
    if not trace_ids:
        trace_ids = _as_non_empty_str_list(claim.get("trace_ids"))

    claim_lineage = claim.get("lineage")
    lineage = claim_lineage if isinstance(claim_lineage, dict) else _as_dict(evidence.get("lineage"))

    claim_security_scans = claim.get("security_scans")
    security_scans = claim_security_scans if isinstance(claim_security_scans, list) else _as_non_empty_dict_list(evidence.get("security_scans"))

    claim_browser_evidence = claim.get("browser_evidence")
    browser_evidence = claim_browser_evidence if isinstance(claim_browser_evidence, list) else _as_non_empty_dict_list(evidence.get("browser_evidence"))

    return {
        "schema_version": claim.get("schema_version", 1),
        "claim_type": claim.get("claim_type", ""),
        "subject": claim.get("subject", ""),
        "artifacts": artifact_refs,
        "trace_ids": trace_ids,
        "lineage": lineage,
        "security_scans": security_scans,
        "browser_evidence": browser_evidence,
    }


def _normalize_artifact_records(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    refs: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                refs.append(cleaned)
            continue
        if not isinstance(item, dict):
            continue
        for field in ("kind", "path", "sha256", "parser", "summary", "trace_id"):
            field_value = str(item.get(field, "")).strip()
            if not field_value:
                raise ValueError(f"claim_artifact_missing_{field}")
        refs.append(str(item.get("path", "")).strip())
    return refs


def _as_non_empty_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_non_empty_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value


def _has_failed_scan(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    failure_tokens = {"fail", "failed", "error", "block", "blocked"}
    for item in value:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip().lower()
        if status in failure_tokens:
            return True
        unresolved_risks = item.get("unresolved_risks")
        if isinstance(unresolved_risks, list) and unresolved_risks:
            return True
    return False
