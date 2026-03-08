from __future__ import annotations

import json
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
