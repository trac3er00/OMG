from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from runtime import artifact_parsers
from runtime.evidence_query import get_evidence_pack


def judge_claims(project_dir: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(project_dir)
    evidence_dir = root / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    aggregate_tokens: list[str] = []

    for index, claim in enumerate(claims):
        run_id = str(claim.get("run_id", "")).strip()
        resolved_claim = dict(claim)

        if run_id:
            evidence_pack = get_evidence_pack(project_dir, run_id)
            trace_ids: list[str] = []
            if isinstance(evidence_pack, dict):
                trace_ids = _as_non_empty_str_list(evidence_pack.get("trace_ids"))
            resolved_claim = {
                **claim,
                "artifacts": [f".omg/evidence/{run_id}.json"],
                "trace_ids": trace_ids,
            }

        result = judge_claim(resolved_claim)
        council_reasons = _load_council_reasons(project_dir=project_dir, run_id=run_id)
        if council_reasons:
            updated_reasons = list(result.get("reasons", []))
            updated_reasons.extend(council_reasons)
            result = {**result, "reasons": updated_reasons, "verdict": "block"}
        result_with_run = {**result, "run_id": run_id}
        results.append(result_with_run)
        aggregate_tokens.append(str(result.get("verdict", "")).strip().lower())

        artifact_run_id = run_id or f"unknown-{index + 1}"
        artifact_path = evidence_dir / f"claim-judge-{_sanitize_run_id(artifact_run_id)}.json"
        artifact_payload = {
            "schema": "ClaimJudgeResult",
            "run_id": run_id,
            "claim": claim,
            "result": result,
        }
        artifact_path.write_text(json.dumps(artifact_payload, indent=2, sort_keys=True), encoding="utf-8")

    verdict = "pass"
    if any(token == "fail" for token in aggregate_tokens):
        verdict = "fail"
    elif any(token == "block" for token in aggregate_tokens):
        verdict = "insufficient"

    return {"schema": "ClaimJudgeResults", "verdict": verdict, "results": results}


def judge_claim(claim: dict[str, Any]) -> dict[str, Any]:
    normalized_claim = _normalize_claim(claim)
    claim_type = str(normalized_claim.get("claim_type", "")).strip()
    subject = str(normalized_claim.get("subject", "")).strip()
    artifacts = _as_non_empty_str_list(normalized_claim.get("artifacts"))
    trace_ids = _as_non_empty_str_list(normalized_claim.get("trace_ids"))
    security_scans = normalized_claim.get("security_scans")
    browser_evidence = normalized_claim.get("browser_evidence")
    causal_chain = _as_dict(normalized_claim.get("causal_chain"))

    reasons: list[dict[str, Any]] = []
    advisories: list[str] = []

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

    raw_artifacts = _extract_artifact_dicts(claim)
    project_dir = str(claim.get("project_dir", "."))
    for artifact in raw_artifacts:
        parse_result = parse_artifact_content(artifact=artifact, project_dir=project_dir)
        if parse_result.get("parsed"):
            continue
        kind = str(parse_result.get("kind", "artifact")).strip().lower() or "artifact"
        error = str(parse_result.get("error", "parse_error")).strip() or "parse_error"
        reasons.append(
            {
                "code": f"artifact_parse_failed_{kind}",
                "message": f"Artifact content parse failed for {kind}: {error}",
                "field": "evidence.artifacts",
            }
        )

    causal_chain_errors = _validate_causal_chain(causal_chain)
    if causal_chain_errors:
        strict_mode = os.environ.get("OMG_PROOF_CHAIN_STRICT", "0").strip() == "1"
        if strict_mode:
            reasons.append(
                {
                    "code": "missing_causal_chain",
                    "message": "Claim must include lock->delta->verification causal chain evidence: "
                    + "; ".join(causal_chain_errors),
                    "field": "causal_chain",
                }
            )
        else:
            advisories.append("claim_judge_causal_chain_missing_permissive")

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
            "causal_chain": causal_chain,
            "advisories": advisories,
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

    lock_verification = claim.get("lock_verification") if isinstance(claim.get("lock_verification"), dict) else _as_dict(evidence.get("lock_verification"))
    causal_chain = {
        "lock_id": str(claim.get("lock_id", evidence.get("lock_id", ""))).strip(),
        "delta_summary": claim.get("delta_summary") if isinstance(claim.get("delta_summary"), dict) else _as_dict(evidence.get("delta_summary")),
        "verification_status": str(claim.get("verification_status", evidence.get("verification_status", ""))).strip(),
        "waiver_artifact_path": str(claim.get("waiver_artifact_path", evidence.get("waiver_artifact_path", ""))).strip(),
        "lock_verification": lock_verification,
    }

    return {
        "schema_version": claim.get("schema_version", 1),
        "claim_type": claim.get("claim_type", ""),
        "subject": claim.get("subject", ""),
        "artifacts": artifact_refs,
        "trace_ids": trace_ids,
        "lineage": lineage,
        "security_scans": security_scans,
        "browser_evidence": browser_evidence,
        "causal_chain": causal_chain,
    }


def _validate_causal_chain(causal_chain: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lock_id = str(causal_chain.get("lock_id", "")).strip()
    delta_summary = causal_chain.get("delta_summary")
    verification_status = str(causal_chain.get("verification_status", "")).strip()
    waiver_artifact_path = str(causal_chain.get("waiver_artifact_path", "")).strip()
    lock_verification = _as_dict(causal_chain.get("lock_verification"))

    if not lock_id:
        errors.append("missing_lock_id")
    if not isinstance(delta_summary, dict) or not delta_summary:
        errors.append("missing_delta_summary")
    if not verification_status:
        errors.append("missing_verification_status")

    lock_status = str(lock_verification.get("status", "")).strip().lower()
    lock_satisfied = lock_status == "ok"
    if not waiver_artifact_path and not lock_satisfied:
        errors.append("missing_waiver_or_lock_satisfied_proof")

    return errors


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


def parse_artifact_content(artifact: dict[str, Any], project_dir: str) -> dict[str, Any]:
    kind = str(artifact.get("kind", "")).strip().lower()
    path_value = str(artifact.get("path", "")).strip()
    if not kind or not path_value:
        return {"parsed": False, "kind": kind or "unknown", "summary": {}, "error": "missing_kind_or_path"}

    parser = _PARSERS.get(kind)
    if parser is None:
        return {"parsed": False, "kind": kind, "summary": {}, "error": "unsupported_artifact_kind"}

    file_path = Path(path_value)
    if not file_path.is_absolute():
        file_path = Path(project_dir) / file_path

    parsed = parser(str(file_path))
    return {
        "parsed": bool(parsed.get("valid")),
        "kind": kind,
        "summary": parsed.get("summary", {}),
        "error": parsed.get("error"),
    }


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


def _extract_artifact_dicts(claim: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = _as_dict(claim.get("evidence"))
    raw_artifacts = evidence.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return []
    return [item for item in raw_artifacts if isinstance(item, dict)]


_PARSERS: dict[str, Any] = {
    "junit": artifact_parsers.parse_junit,
    "sarif": artifact_parsers.parse_sarif,
    "coverage": artifact_parsers.parse_coverage,
    "browser_trace": artifact_parsers.parse_browser_trace,
    "diff_hunk": artifact_parsers.parse_diff_hunk,
}


def _sanitize_run_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    return cleaned or "unknown"


def _load_council_reasons(project_dir: str, run_id: str) -> list[dict[str, Any]]:
    if not run_id:
        return []
    path = Path(project_dir) / ".omg" / "state" / "council_verdicts" / f"{run_id}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []

    verdicts = _as_dict(payload.get("verdicts"))
    evidence_completeness = _as_dict(verdicts.get("evidence_completeness"))
    verdict = str(evidence_completeness.get("verdict", "")).strip().lower()
    if verdict not in {"fail", "block", "blocked", "error"}:
        return []
    findings = evidence_completeness.get("findings")
    finding_items = findings if isinstance(findings, list) else []
    message = "council evidence completeness failed"
    if finding_items:
        message = "; ".join(str(item).strip() for item in finding_items if str(item).strip()) or message
    return [
        {
            "code": "council_evidence_incomplete",
            "message": message,
            "field": "council_verdicts.evidence_completeness",
        }
    ]
