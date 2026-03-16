from __future__ import annotations

from importlib import import_module
from typing import Any


def _normalize_verdict_payload(payload: dict[str, Any]) -> dict[str, Any]:
    module = import_module("runtime.verdict_schema")
    return dict(module.normalize_verdict(payload))


def format_review_payload(evidence: dict[str, Any], *, inline_batch_limit: int = 20) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {
            "status": "error",
            "error_code": "GITHUB_REVIEW_EVIDENCE_INVALID",
            "message": "Review evidence must be a JSON object.",
        }

    artifacts = _as_str_list(evidence.get("artifacts"))
    if not artifacts:
        return {
            "status": "error",
            "error_code": "GITHUB_REVIEW_ARTIFACTS_MISSING",
            "message": "Review evidence is missing required artifacts.",
        }

    normalized_verdict = _normalize_verdict_payload(evidence)
    raw_verdict = normalized_verdict["status"]
    review_status = _normalize_review_status(raw_verdict)
    review_event = _review_event_for_status(review_status)

    checks = _normalize_checks(evidence.get("checks"))
    evidence_gaps = list(normalized_verdict.get("blockers", []))
    if not evidence_gaps:
        evidence_gaps = _as_str_list(evidence.get("evidence_gaps"))
    if not evidence_gaps:
        evidence_gaps = _as_str_list(evidence.get("unresolved_risks"))

    raw_inline = evidence.get("inline_comments")
    inline_comments = _normalize_inline_comments(raw_inline)

    limit = max(0, int(inline_batch_limit))
    selected_comments = inline_comments[:limit]
    dropped_comments = max(0, len(inline_comments) - len(selected_comments))
    body = _build_review_body(
        review_status=review_status,
        raw_verdict=raw_verdict,
        artifacts=artifacts,
        checks=checks,
        evidence_gaps=evidence_gaps,
        dropped_comments=dropped_comments,
    )

    changed_files = _as_str_list(evidence.get("changed_files"))
    categories = _as_str_list(evidence.get("categories"))
    goal = str(evidence.get("goal", "")).strip()
    pr_risk: dict[str, Any] = {}
    if changed_files or categories:
        from runtime.delta_classifier import compute_pr_risk_payload
        pr_risk = compute_pr_risk_payload(
            changed_files=changed_files,
            categories=categories,
            goal=goal,
            evidence=evidence,
        )

    return {
        "status": "ok",
        "review_status": review_status,
        "review_event": review_event,
        "body": body,
        "inline_comments": selected_comments,
        "dropped_inline_comments": dropped_comments,
        "pr_risk": pr_risk,
    }


def _build_review_body(
    *,
    review_status: str,
    raw_verdict: str,
    artifacts: list[str],
    checks: list[dict[str, str]],
    evidence_gaps: list[str],
    dropped_comments: int,
) -> str:
    lines: list[str] = [
        "## OMG PR Reviewer",
        "",
        f"- CI verdict: **{raw_verdict or review_status}**",
        f"- Review state: **{review_status}**",
        "",
        "### Evidence Artifacts",
    ]
    for artifact in artifacts:
        lines.append(f"- `{artifact}`")

    lines.append("")
    lines.append("### CI Checks")
    if checks:
        for check in checks:
            name = check.get("name", "check")
            status = check.get("status", "unknown")
            detail = check.get("detail", "")
            lines.append(f"- {name}: {status}" + (f" ({detail})" if detail else ""))
    else:
        lines.append("- No check details were provided by CI artifacts.")

    lines.append("")
    lines.append("### Evidence Gaps")
    if evidence_gaps:
        for gap in evidence_gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- None reported.")

    if dropped_comments > 0:
        lines.append("")
        lines.append(f"- Inline comments truncated to API-safe batch size; omitted: {dropped_comments}")

    lines.append("")
    lines.append("This review reports CI verdicts and evidence completeness only.")
    return "\n".join(lines)


def _normalize_review_status(verdict: str) -> str:
    if verdict in {"ok", "pass", "passed", "success", "approved"}:
        return "approved"
    if verdict in {"fail", "failed", "error", "reject", "rejected", "block", "blocked"}:
        return "rejected"
    return "pending"


def _review_event_for_status(status: str) -> str:
    if status == "approved":
        return "APPROVE"
    if status == "rejected":
        return "REQUEST_CHANGES"
    return "COMMENT"


def _normalize_checks(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    checks: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        status = str(item.get("status", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if not name and not status:
            continue
        checks.append({"name": name or "check", "status": status or "unknown", "detail": detail})
    return checks


def _normalize_inline_comments(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    comments: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        body = str(item.get("body", "")).strip()
        line = item.get("line")
        if not path or not body:
            continue
        if not isinstance(line, int) or line <= 0:
            continue
        comments.append({"path": path, "line": line, "body": body})
    return comments


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


__all__ = ["format_review_payload"]
