from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from runtime import artifact_parsers
from runtime.evidence_requirements import FULL_REQUIREMENTS, requirements_for_profile
from runtime.verdict_schema import resolve_conclusion


_REQUIRED_ARTIFACT_FIELDS = ("kind", "path", "sha256", "parser", "summary", "trace_id")
_PRODUCTION_REQUIRED_PRIMITIVES = ("claim_judge", "proof_gate", "test_intent_lock")

_REQUIRED_ARTIFACT_TOKENS: dict[str, tuple[str, ...]] = {
    "junit": ("junit", "junit.xml", "surefire"),
    "coverage": ("coverage", "lcov", "coverage.xml"),
    "sarif": ("sarif", ".sarif"),
    "browser_trace": ("trace.zip", "browser_trace", "playwright", "browser-evidence"),
}


def required_production_primitives() -> tuple[str, ...]:
    return _PRODUCTION_REQUIRED_PRIMITIVES


def production_gate(evidence: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(evidence)
    blockers: list[str] = []

    primitive_payload = _as_dict(payload.get("claim_judge"))
    if not primitive_payload:
        blockers.append("production_gate_missing_claim_judge")
    else:
        status = str(primitive_payload.get("status", "")).strip().lower()
        verdict = str(primitive_payload.get("claim_judge_verdict", primitive_payload.get("verdict", ""))).strip().lower()
        if status in {"blocked", "error", "fail", "insufficient"} or verdict in {"blocked", "error", "fail", "insufficient"}:
            blockers.append("production_gate_claim_judge_blocked")

    proof_result = _as_dict(payload.get("proof_gate"))
    if not proof_result:
        try:
            proof_result = evaluate_proof_gate(payload)
        except Exception:
            proof_result = {"verdict": "fail", "blockers": ["proof_gate_internal_error"]}

    if not proof_result:
        blockers.append("production_gate_missing_proof_gate")
    else:
        proof_verdict = str(proof_result.get("verdict", "")).strip().lower()
        if proof_verdict != "pass":
            proof_blockers = proof_result.get("blockers")
            if isinstance(proof_blockers, list) and proof_blockers:
                blockers.extend(
                    f"production_gate_proof_gate:{str(item).strip()}"
                    for item in proof_blockers
                    if str(item).strip()
                )
            else:
                blockers.append("production_gate_proof_gate_failed")

    lock_payload = _as_dict(payload.get("test_intent_lock"))
    if not lock_payload:
        blockers.append("production_gate_missing_test_intent_lock")
    else:
        lock_status = str(lock_payload.get("status", "")).strip().lower()
        lock_id = str(lock_payload.get("lock_id", "")).strip()
        if lock_status in {"blocked", "error", "fail", "insufficient"} or (lock_status not in {"ok", "allowed"} and not lock_id):
            blockers.append("production_gate_test_intent_lock_unsatisfied")

    unique_blockers = list(dict.fromkeys(item for item in blockers if str(item).strip()))
    # Evidence exists if all required primitives are present and not blocked
    evidence_exists = bool(primitive_payload and proof_result and lock_payload)
    if unique_blockers:
        conclusion = resolve_conclusion("fail", evidence_exists)
        return {
            "status": "blocked",
            "conclusion": conclusion,
            "blockers": unique_blockers,
            "required_primitives": list(_PRODUCTION_REQUIRED_PRIMITIVES),
        }
    conclusion = resolve_conclusion("pass", evidence_exists)
    return {
        "status": "ok",
        "conclusion": conclusion,
        "required_primitives": list(_PRODUCTION_REQUIRED_PRIMITIVES),
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
    verdict = "pass" if not unique_blockers else "fail"
    evidence_exists = bool(claims and (trace_id or evidence_pack))
    conclusion = resolve_conclusion(verdict, evidence_exists)
    return {
        "schema": "ProofGateResult",
        "verdict": verdict,
        "conclusion": conclusion,
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


# NF4b: Lane evidence collection


def detect_lane(
    project_dir: str,
    commit_messages: list[str] | None = None,
    pr_labels: list[str] | None = None,
    files: list[str] | None = None,
) -> str:
    """Auto-detect the certification lane from context.

    Returns the lane ID string based on file patterns, commit messages, and PR labels.
    """
    messages = commit_messages or []
    labels = pr_labels or []
    file_list = files or []

    messages_lower = [m.lower() for m in messages]
    labels_lower = [lb.lower() for lb in labels]
    files_lower = [f.lower() for f in file_list]

    # Check for regression/revert first (specific pattern)
    regression_keywords = {"regression", "revert"}
    for msg in messages_lower:
        if any(kw in msg for kw in regression_keywords):
            return "lane-regression-recovery"

    # Check for security-related files or commit messages
    security_file_patterns = {".sarif"}
    security_keywords = {"cve", "security", "vuln"}
    has_security_files = any(
        any(pattern in f for pattern in security_file_patterns) for f in files_lower
    )
    has_security_keywords = any(
        any(kw in msg for kw in security_keywords) for msg in messages_lower
    )
    if has_security_files or has_security_keywords:
        return "lane-security-remediation"

    # Check for migration/refactor patterns
    migration_file_patterns = {"migration", "dockerfile"}
    migration_keywords = {"migrate", "upgrade"}
    has_migration_files = any(
        any(pattern in f for pattern in migration_file_patterns) for f in files_lower
    )
    has_migration_keywords = any(
        any(kw in msg for kw in migration_keywords) for msg in messages_lower
    )
    if has_migration_files or has_migration_keywords:
        return "lane-migration-refactor"

    # Check for bug fix patterns
    test_file_patterns = {"test_", "_test."}
    fix_keywords = {"fix", "bug"}
    has_test_files = any(
        any(pattern in f for pattern in test_file_patterns) for f in files_lower
    )
    has_fix_keywords = any(
        any(kw in msg for kw in fix_keywords) for msg in messages_lower
    )
    if has_test_files and has_fix_keywords:
        return "lane-bug-fix"

    # Check for feature label or default
    if any("feature" in lb for lb in labels_lower):
        return "lane-feature-ship"

    # Default to feature-ship
    return "lane-feature-ship"


def collect_lane_evidence(project_dir: str, lane_id: str, run_id: str) -> dict[str, Any]:
    """Collect evidence for a certification lane.

    Looks up the lane's evidence requirements from CERTIFICATION_LANES,
    checks which requirements are met, and writes evidence to
    `.omg/evidence/lane-<lane_id>-<run_id>.json`.

    Returns:
        dict with lane, requirements, met, missing, and completeness fields.
    """
    from runtime.evidence_requirements import CERTIFICATION_LANES, EVIDENCE_REQUIREMENTS_BY_PROFILE

    root = Path(project_dir)
    evidence_dir = root / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Get lane metadata and requirements
    lane_metadata = CERTIFICATION_LANES.get(lane_id, {})
    requirements = EVIDENCE_REQUIREMENTS_BY_PROFILE.get(lane_id, [])

    met: list[str] = []
    missing: list[str] = []

    # Check each requirement
    for req in requirements:
        if _check_requirement_met(root, req, run_id):
            met.append(req)
        else:
            missing.append(req)

    completeness = len(met) / len(requirements) if requirements else 0.0

    result = {
        "schema": "LaneEvidence",
        "lane": lane_id,
        "lane_label": lane_metadata.get("label", lane_id),
        "gate_type": lane_metadata.get("gate_type", "unknown"),
        "run_id": run_id,
        "requirements": list(requirements),
        "met": met,
        "missing": missing,
        "completeness": completeness,
    }

    # Write evidence file
    evidence_filename = f"lane-{lane_id}-{run_id}.json"
    evidence_path = evidence_dir / evidence_filename
    import json
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    return result


def _check_requirement_met(root: Path, requirement: str, run_id: str) -> bool:
    """Check if a single requirement is met based on evidence files."""
    evidence_dir = root / ".omg" / "evidence"

    requirement_checks: dict[str, list[str]] = {
        "tests": ["junit.xml", f"junit-{run_id}.xml", "test-results.json"],
        "lsp_clean": ["lsp-check.json", f"lsp-{run_id}.json", "lsp-clean.json"],
        "build": ["build.json", f"build-{run_id}.json", "build-log.json"],
        "provenance": ["provenance.json", f"provenance-{run_id}.json", "sbom.json"],
        "trace_link": ["trace.json", f"trace-{run_id}.json", "tracebank.json"],
        "security_scan": ["security-check.json", f"security-{run_id}.json", "results.sarif"],
        "license_scan": ["license-scan.json", f"license-{run_id}.json"],
        "sbom": ["sbom.json", f"sbom-{run_id}.json"],
        "trust_scores": ["trust-scores.json", f"trust-{run_id}.json"],
        "artifact_contracts": ["contracts.json", f"contracts-{run_id}.json"],
        "signed_lineage": ["lineage.json", f"lineage-{run_id}.json"],
        "signed_model_card": ["model-card.json", f"model-card-{run_id}.json"],
        "signed_checkpoint": ["checkpoint.json", f"checkpoint-{run_id}.json"],
    }

    patterns = requirement_checks.get(requirement, [])
    for pattern in patterns:
        if (evidence_dir / pattern).exists():
            return True

    # Also check for run-specific evidence pack
    evidence_pack = evidence_dir / f"{run_id}.json"
    if evidence_pack.exists():
        try:
            import json
            content = json.loads(evidence_pack.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                # Check if evidence pack indicates this requirement is met
                if requirement in content.get("met_requirements", []):
                    return True
                # Check artifacts field
                artifacts = content.get("artifacts", [])
                if isinstance(artifacts, list):
                    artifact_kinds = [
                        str(a.get("kind", "")).lower() for a in artifacts if isinstance(a, dict)
                    ]
                    if requirement in artifact_kinds:
                        return True
        except (OSError, json.JSONDecodeError):
            pass

    return False


# NF4c: Lane rendering


def render_lane_status(project_dir: str) -> str:
    """Render lane status as a formatted table.

    Reads all lane evidence files from `.omg/evidence/lane-*.json`
    and formats them as a table.

    Returns:
        Formatted table string showing lane status and completeness.
    """
    import json
    from runtime.evidence_requirements import CERTIFICATION_LANES

    root = Path(project_dir)
    evidence_dir = root / ".omg" / "evidence"

    if not evidence_dir.exists():
        return "No lane evidence found."

    lane_files = sorted(evidence_dir.glob("lane-*.json"))
    if not lane_files:
        return "No lane evidence found."

    # Aggregate evidence by lane
    lane_data: dict[str, dict[str, Any]] = {}
    for lane_file in lane_files:
        try:
            content = json.loads(lane_file.read_text(encoding="utf-8"))
            if not isinstance(content, dict):
                continue
            lane_id = str(content.get("lane", "")).strip()
            if not lane_id:
                continue

            # Keep the most recent evidence for each lane (last file wins)
            lane_data[lane_id] = content
        except (OSError, json.JSONDecodeError):
            continue

    if not lane_data:
        return "No valid lane evidence found."

    # Build table
    lines: list[str] = []
    header = f"{'Lane':<25} | {'Status':<10} | {'Completeness':<12}"
    separator = "-" * len(header)
    lines.append(header)
    lines.append(separator)

    for lane_id, data in sorted(lane_data.items()):
        label = str(data.get("lane_label", lane_id)).strip()
        gate_type = str(data.get("gate_type", "unknown")).strip()

        # Determine status based on gate_type
        if gate_type == "active-gated":
            status = "Active"
        elif gate_type == "active-advisory":
            status = "Advisory"
        else:
            status = "Unknown"

        completeness = data.get("completeness", 0.0)
        completeness_pct = f"{completeness * 100:.0f}%"

        # Use label for display, trim if needed
        display_label = label if len(label) <= 25 else label[:22] + "..."
        lines.append(f"{display_label:<25} | {status:<10} | {completeness_pct:<12}")

    return "\n".join(lines)
