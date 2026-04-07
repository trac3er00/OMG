"""Evidence-backed claim validation for OMG runtime and release gates.

This module evaluates completion/release claims against required evidence,
including artifact references, trace links, security scan outcomes, and
causal-chain metadata. It emits deterministic verdicts (pass/fail/block),
persists per-claim result artifacts, and can merge additional council-level
evidence-completeness findings into the final decision.
"""

from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from typing import Any

from registry.verify_artifact import verify_artifact_statement
from runtime import artifact_parsers
from runtime.context_engine import load_profile_digest
from runtime.evidence_query import get_evidence_pack
from runtime.evidence_requirements import (
    FULL_REQUIREMENTS,
    normalize_profile,
    resolve_profile,
    requirements_for_profile,
)


def judge_claims(project_dir: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a batch of claims and persist claim-judge result artifacts.

    For each claim, this function optionally resolves run-scoped evidence pack
    metadata, evaluates the claim, merges council evidence findings, writes a
    per-claim artifact under ``.omg/evidence/``, and computes an aggregate
    verdict for the full batch.

    Args:
        project_dir: Project root that contains ``.omg`` state/evidence paths.
        claims: Claim payloads to evaluate.

    Returns:
        Aggregate claim-judge result payload with per-claim verdicts and
        advisory profile digest context.
    """
    root = Path(project_dir)
    evidence_dir = root / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    profile_digest = load_profile_digest(project_dir)

    results: list[dict[str, Any]] = []
    aggregate_tokens: list[str] = []

    for index, claim in enumerate(claims):
        run_id = str(claim.get("run_id", "")).strip()
        resolved_claim = dict(claim)

        if run_id:
            evidence_pack = get_evidence_pack(project_dir, run_id)
            trace_ids: list[str] = []
            context_checksum = ""
            profile_version = ""
            intent_gate_version = ""
            evidence_profile = ""
            if isinstance(evidence_pack, dict):
                trace_ids = _as_non_empty_str_list(evidence_pack.get("trace_ids"))
                context_checksum = str(
                    evidence_pack.get("context_checksum", "")
                ).strip()
                profile_version = str(evidence_pack.get("profile_version", "")).strip()
                intent_gate_version = str(
                    evidence_pack.get("intent_gate_version", "")
                ).strip()
                evidence_profile = str(
                    evidence_pack.get("evidence_profile", "")
                ).strip()
            resolved_claim = {
                **claim,
                "artifacts": [f".omg/evidence/{run_id}.json"],
                "trace_ids": trace_ids,
                "context_checksum": context_checksum,
                "profile_version": profile_version,
                "intent_gate_version": intent_gate_version,
                "evidence_profile": evidence_profile,
            }

        result = judge_claim(resolved_claim)
        council_reasons = _load_council_reasons(project_dir=project_dir, run_id=run_id)
        if council_reasons:
            updated_reasons = list(result.get("reasons", []))
            updated_reasons.extend(council_reasons)
            result = {**result, "reasons": updated_reasons, "verdict": "block"}
        result_with_run = {**result, "run_id": run_id}
        result_with_run["context_checksum"] = str(
            resolved_claim.get("context_checksum", "")
        ).strip()
        result_with_run["profile_version"] = str(
            resolved_claim.get("profile_version", "")
        ).strip()
        result_with_run["intent_gate_version"] = str(
            resolved_claim.get("intent_gate_version", "")
        ).strip()
        result_with_run["advisory_context"] = {"profile_digest": profile_digest}
        results.append(result_with_run)
        aggregate_tokens.append(str(result.get("verdict", "")).strip().lower())

        artifact_run_id = run_id or f"unknown-{index + 1}"
        artifact_path = (
            evidence_dir / f"claim-judge-{_sanitize_run_id(artifact_run_id)}.json"
        )
        artifact_payload = {
            "schema": "ClaimJudgeResult",
            "run_id": run_id,
            "claim": claim,
            "result": result,
            "context_checksum": str(resolved_claim.get("context_checksum", "")).strip(),
            "profile_version": str(resolved_claim.get("profile_version", "")).strip(),
            "intent_gate_version": str(
                resolved_claim.get("intent_gate_version", "")
            ).strip(),
            "advisory_context": {"profile_digest": profile_digest},
        }
        artifact_path.write_text(
            json.dumps(artifact_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    verdict = "pass"
    if any(token == "fail" for token in aggregate_tokens):
        verdict = "fail"
    elif any(token == "block" for token in aggregate_tokens):
        verdict = "insufficient"

    return {
        "schema": "ClaimJudgeResults",
        "verdict": verdict,
        "results": results,
        "advisory_context": {"profile_digest": profile_digest},
    }


def evaluate_claims_for_release(
    project_dir: str,
    run_id: str,
    claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate release claims and map verdicts to allow/block status.

    Args:
        project_dir: Project root used for claim evaluation.
        run_id: Run identifier used when default release claims are generated.
        claims: Optional explicit claims. When omitted, a default
            ``release_ready`` claim is evaluated.

    Returns:
        Decision payload with ``status`` set to ``allowed`` or ``blocked`` and
        the underlying claim-judge result attached.
    """
    candidate_claims = (
        claims
        if isinstance(claims, list) and claims
        else [
            {
                "claim_type": "release_ready",
                "run_id": run_id,
                "evidence_profile": "release",
            }
        ]
    )
    judged = judge_claims(project_dir, candidate_claims)
    verdict = str(judged.get("verdict", "")).strip().lower()
    if verdict in {"fail", "insufficient", "block", "blocked", "error"}:
        return {
            "status": "blocked",
            "authority": "claim_judge",
            "reason": f"claim_judge_verdict={verdict}",
            "claim_judge_verdict": verdict,
            "claim_judge": judged,
        }
    return {
        "status": "allowed",
        "authority": "claim_judge",
        "reason": f"claim_judge_verdict={verdict or 'pass'}",
        "claim_judge_verdict": verdict or "pass",
        "claim_judge": judged,
    }


def judge_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single claim against evidence and policy requirements.

    The evaluation pipeline normalizes claim shape, resolves evidence-profile
    requirements, checks mandatory artifacts/trace links, validates security and
    browser evidence, parses structured artifact content, enforces excluded
    failure waiver policy, and validates lock->delta->verification causal chain
    fields. Verdict priority is fail > block > pass.

    Args:
        claim: Claim payload to validate.

    Returns:
        Claim-level verdict payload including failure/block reasons and
        normalized evidence context.
    """
    normalized_claim = _normalize_claim(claim)
    claim_type = str(normalized_claim.get("claim_type", "")).strip()
    subject = str(normalized_claim.get("subject", "")).strip()
    run_id = str(claim.get("run_id", "")).strip()
    artifacts = _as_non_empty_str_list(normalized_claim.get("artifacts"))
    trace_ids = _as_non_empty_str_list(normalized_claim.get("trace_ids"))
    security_scans = normalized_claim.get("security_scans")
    browser_evidence = normalized_claim.get("browser_evidence")
    excluded_failures = _as_non_empty_list(normalized_claim.get("excluded_failures"))
    excluded_failures_waiver_path = str(
        normalized_claim.get("excluded_failures_waiver_path", "")
    ).strip()
    evidence_profile = str(normalized_claim.get("evidence_profile", "")).strip()
    evidence_requirements, evidence_profile_error = _resolve_evidence_requirements(
        evidence_profile
    )
    requirement_set = {
        str(item).strip() for item in evidence_requirements if str(item).strip()
    }
    causal_chain = _as_dict(normalized_claim.get("causal_chain"))

    reasons: list[dict[str, Any]] = []
    advisories: list[str] = []

    if evidence_profile_error:
        reasons.append(evidence_profile_error)

    if "tests" in requirement_set and not artifacts:
        reasons.append(
            {
                "code": "missing_artifacts",
                "message": "Claim must include at least one evidence artifact reference.",
                "field": "artifacts",
            }
        )

    if "trace_link" in requirement_set and not trace_ids:
        reasons.append(
            {
                "code": "missing_trace_ids",
                "message": "Claim must include at least one trace identifier.",
                "field": "trace_ids",
            }
        )

    if "security_scan" in requirement_set and _has_failed_scan(security_scans):
        reasons.append(
            {
                "code": "security_scan_failed",
                "message": "Security scans report unresolved failures; claim is blocked.",
                "field": "security_scans",
            }
        )

    if requirement_set == set(FULL_REQUIREMENTS) and _has_failed_scan(browser_evidence):
        reasons.append(
            {
                "code": "browser_evidence_failed",
                "message": "Browser evidence reports failed checks; claim is blocked.",
                "field": "browser_evidence",
            }
        )

    raw_artifacts = _extract_artifact_dicts(claim)
    project_dir = str(claim.get("project_dir", "."))
    proof_score_evidence = _build_proof_score_evidence(
        artifacts=artifacts, raw_artifacts=raw_artifacts
    )
    for artifact in raw_artifacts:
        parse_result = parse_artifact_content(
            artifact=artifact, project_dir=project_dir
        )
        for evidence_item in proof_score_evidence:
            if evidence_item.get("path") == artifact.get("path") and evidence_item.get(
                "type"
            ) == artifact.get("kind"):
                evidence_item["valid"] = bool(parse_result.get("parsed"))
                break
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

    reasons.extend(
        _validate_excluded_failures_policy(
            project_dir=project_dir,
            run_id=run_id,
            excluded_failures=excluded_failures,
            waiver_path=excluded_failures_waiver_path,
        )
    )

    strict_mode = os.environ.get("OMG_PROOF_CHAIN_STRICT", "0").strip() == "1"
    strict_causal_chain = strict_mode or _claim_type_enforces_strict_causal_chain(
        claim_type=claim_type,
        claim=claim,
    )

    causal_chain_errors = _validate_causal_chain(
        causal_chain, require_versions=strict_causal_chain
    )
    if causal_chain_errors:
        if strict_causal_chain:
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

    result = {
        "schema": "ClaimJudgeResult",
        "verdict": verdict,
        "reasons": reasons,
        "claim_type": claim_type,
        "subject": subject,
        "evidence": {
            "artifacts": artifacts,
            "trace_ids": trace_ids,
            "lineage": normalized_claim.get("lineage")
            if isinstance(normalized_claim.get("lineage"), dict)
            else {},
            "security_scans": security_scans
            if isinstance(security_scans, list)
            else [],
            "browser_evidence": browser_evidence
            if isinstance(browser_evidence, list)
            else [],
            "excluded_failures": excluded_failures,
            "excluded_failures_waiver_path": excluded_failures_waiver_path,
            "causal_chain": causal_chain,
            "advisories": advisories,
            "evidence_profile": evidence_profile,
            "evidence_requirements": list(evidence_requirements),
        },
    }
    try:
        compute_score = import_module("runtime.proof_score").compute_score
        result["proofScore"] = compute_score(proof_score_evidence)
    except Exception:
        pass
    return result


def _normalize_claim(claim: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_dict(claim.get("evidence"))
    artifact_refs = _as_non_empty_str_list(claim.get("artifacts"))
    artifact_refs.extend(_normalize_artifact_records(evidence.get("artifacts")))

    trace_ids = _as_non_empty_str_list(evidence.get("trace_ids"))
    if not trace_ids:
        trace_ids = _as_non_empty_str_list(claim.get("trace_ids"))

    claim_lineage = claim.get("lineage")
    lineage = (
        claim_lineage
        if isinstance(claim_lineage, dict)
        else _as_dict(evidence.get("lineage"))
    )

    claim_security_scans = claim.get("security_scans")
    security_scans = (
        claim_security_scans
        if isinstance(claim_security_scans, list)
        else _as_non_empty_dict_list(evidence.get("security_scans"))
    )

    claim_browser_evidence = claim.get("browser_evidence")
    browser_evidence = (
        claim_browser_evidence
        if isinstance(claim_browser_evidence, list)
        else _as_non_empty_dict_list(evidence.get("browser_evidence"))
    )

    claim_excluded_failures = claim.get("excluded_failures")
    excluded_failures = (
        claim_excluded_failures
        if isinstance(claim_excluded_failures, list)
        else _as_non_empty_list(evidence.get("excluded_failures"))
    )

    excluded_failures_waiver_path = str(
        claim.get(
            "excluded_failures_waiver_path",
            evidence.get("excluded_failures_waiver_path", ""),
        )
    ).strip()

    lock_verification = (
        claim.get("lock_verification")
        if isinstance(claim.get("lock_verification"), dict)
        else _as_dict(evidence.get("lock_verification"))
    )
    causal_chain = {
        "lock_id": str(claim.get("lock_id", evidence.get("lock_id", ""))).strip(),
        "delta_summary": claim.get("delta_summary")
        if isinstance(claim.get("delta_summary"), dict)
        else _as_dict(evidence.get("delta_summary")),
        "verification_status": str(
            claim.get("verification_status", evidence.get("verification_status", ""))
        ).strip(),
        "waiver_artifact_path": str(
            claim.get("waiver_artifact_path", evidence.get("waiver_artifact_path", ""))
        ).strip(),
        "lock_verification": lock_verification,
        "context_checksum": str(
            claim.get("context_checksum", evidence.get("context_checksum", ""))
        ).strip(),
        "profile_version": str(
            claim.get("profile_version", evidence.get("profile_version", ""))
        ).strip(),
        "intent_gate_version": str(
            claim.get("intent_gate_version", evidence.get("intent_gate_version", ""))
        ).strip(),
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
        "excluded_failures": excluded_failures,
        "excluded_failures_waiver_path": excluded_failures_waiver_path,
        "causal_chain": causal_chain,
        "evidence_profile": normalize_profile(
            str(
                claim.get("evidence_profile", evidence.get("evidence_profile", ""))
            ).strip()
        ),
    }


def _resolve_evidence_requirements(
    evidence_profile: str,
) -> tuple[list[str], dict[str, Any] | None]:
    raw_profile = str(evidence_profile or "").strip()
    normalized = normalize_profile(raw_profile) if raw_profile else ""

    try:
        canonical = resolve_profile(normalized or None)
        return requirements_for_profile(canonical), None
    except ValueError as exc:
        payload = _parse_profile_error(exc)
        reason = {
            "code": "unknown_evidence_profile",
            "message": str(payload.get("reason", "unknown_profile")),
            "field": "evidence_profile",
            "profile": str(payload.get("profile", raw_profile)).strip(),
        }
        return list(FULL_REQUIREMENTS), reason


def _parse_profile_error(exc: ValueError) -> dict[str, Any]:
    raw = str(exc).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _validate_excluded_failures_policy(
    *,
    project_dir: str,
    run_id: str,
    excluded_failures: list[Any],
    waiver_path: str,
) -> list[dict[str, Any]]:
    if not excluded_failures:
        return []

    if not waiver_path:
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures require a signed waiver artifact.",
                "field": "excluded_failures",
            }
        ]

    waiver_file = Path(waiver_path)
    if not waiver_file.is_absolute():
        waiver_file = Path(project_dir) / waiver_file
    if not waiver_file.exists():
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": f"Excluded failures waiver artifact not found: {waiver_path}",
                "field": "excluded_failures_waiver_path",
            }
        ]

    try:
        waiver_payload = json.loads(waiver_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        waiver_payload = None
    if not isinstance(waiver_payload, dict):
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures waiver artifact must be valid JSON.",
                "field": "excluded_failures_waiver_path",
            }
        ]

    statement = _extract_signed_statement(waiver_payload)
    if not isinstance(statement, dict) or not verify_artifact_statement(statement):
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures waiver artifact must include a valid signed attestation statement.",
                "field": "excluded_failures_waiver_path",
            }
        ]

    waiver_run_id = str(waiver_payload.get("run_id", "")).strip()
    if run_id and waiver_run_id and waiver_run_id != run_id:
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures waiver artifact run_id does not match claim run_id.",
                "field": "excluded_failures_waiver_path",
            }
        ]

    waiver_exclusions = _as_non_empty_list(waiver_payload.get("excluded_failures"))
    if not waiver_exclusions:
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures waiver artifact must enumerate excluded failures.",
                "field": "excluded_failures_waiver_path",
            }
        ]

    required = {_normalize_exclusion_token(item) for item in excluded_failures}
    provided = {_normalize_exclusion_token(item) for item in waiver_exclusions}
    if not required.issubset(provided):
        return [
            {
                "code": "excluded_failures_without_signed_waiver",
                "message": "Excluded failures waiver artifact does not authorize all excluded failures.",
                "field": "excluded_failures",
            }
        ]
    return []


def _extract_signed_statement(payload: dict[str, Any]) -> dict[str, Any] | None:
    if "_type" in payload and "subject" in payload and "predicateType" in payload:
        return payload
    candidate = payload.get("attestation_statement")
    if isinstance(candidate, dict):
        return candidate
    candidate = payload.get("statement")
    if isinstance(candidate, dict):
        return candidate
    candidate = payload.get("attestation")
    if isinstance(candidate, dict):
        return candidate
    return None


def _normalize_exclusion_token(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for field in ("id", "test", "name", "reason"):
            token = str(value.get(field, "")).strip()
            if token:
                return token
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return str(value).strip()


def _validate_causal_chain(
    causal_chain: dict[str, Any], *, require_versions: bool
) -> list[str]:
    errors: list[str] = []
    lock_id = str(causal_chain.get("lock_id", "")).strip()
    delta_summary = causal_chain.get("delta_summary")
    verification_status = str(causal_chain.get("verification_status", "")).strip()
    waiver_artifact_path = str(causal_chain.get("waiver_artifact_path", "")).strip()
    context_checksum = str(causal_chain.get("context_checksum", "")).strip()
    profile_version = str(causal_chain.get("profile_version", "")).strip()
    intent_gate_version = str(causal_chain.get("intent_gate_version", "")).strip()
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

    if require_versions:
        if not context_checksum:
            errors.append("missing_context_checksum")
        if not profile_version:
            errors.append("missing_profile_version")
        if not intent_gate_version:
            errors.append("missing_intent_gate_version")

    return errors


def _claim_type_enforces_strict_causal_chain(
    *, claim_type: str, claim: dict[str, Any]
) -> bool:
    mode = str(claim.get("causal_chain_mode", "")).strip().lower()
    if mode == "legacy":
        return False
    if mode == "strict":
        return True

    if isinstance(claim.get("require_causal_chain"), bool):
        return bool(claim.get("require_causal_chain"))

    normalized = claim_type.strip().lower()
    if not normalized:
        return False
    tokens = {item for item in normalized.replace("-", "_").split("_") if item}
    return bool(tokens & {"runtime", "council"})


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


def parse_artifact_content(
    artifact: dict[str, Any], project_dir: str
) -> dict[str, Any]:
    """Parse a typed evidence artifact via the registered parser map.

    Args:
        artifact: Artifact descriptor containing ``kind`` and ``path``.
        project_dir: Base directory used to resolve relative artifact paths.

    Returns:
        Parse status payload with ``parsed`` flag, normalized ``kind``, parsed
        summary, and parser error when parsing fails.
    """
    kind = str(artifact.get("kind", "")).strip().lower()
    path_value = str(artifact.get("path", "")).strip()
    if not kind or not path_value:
        return {
            "parsed": False,
            "kind": kind or "unknown",
            "summary": {},
            "error": "missing_kind_or_path",
        }

    parser = _PARSERS.get(kind)
    if parser is None:
        return {
            "parsed": False,
            "kind": kind,
            "summary": {},
            "error": "unsupported_artifact_kind",
        }

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


def _as_non_empty_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    items: list[Any] = []
    for item in value:
        if isinstance(item, str) and not item.strip():
            continue
        if item in ({}, []):
            continue
        items.append(item)
    return items


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


def _build_proof_score_evidence(
    *, artifacts: list[str], raw_artifacts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if raw_artifacts:
        return [
            {
                "type": str(item.get("kind", "")).strip(),
                "path": str(item.get("path", "")).strip(),
                "valid": True,
            }
            for item in raw_artifacts
        ]
    return [
        {
            "type": "artifact",
            "path": artifact,
            "valid": True,
        }
        for artifact in artifacts
        if artifact
    ]


_PARSERS: dict[str, Any] = {
    "junit": artifact_parsers.parse_junit,
    "sarif": artifact_parsers.parse_sarif,
    "coverage": artifact_parsers.parse_coverage,
    "browser_trace": artifact_parsers.parse_browser_trace,
    "diff_hunk": artifact_parsers.parse_diff_hunk,
}


def _sanitize_run_id(value: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip()
    )
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
        message = (
            "; ".join(str(item).strip() for item in finding_items if str(item).strip())
            or message
        )
    return [
        {
            "code": "council_evidence_incomplete",
            "message": message,
            "field": "council_verdicts.evidence_completeness",
        }
    ]
