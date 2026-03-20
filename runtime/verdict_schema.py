from __future__ import annotations

from typing import Any, Literal, TypedDict

VerdictStatus = Literal["pass", "fail", "action_required", "pending"]
ConclusionState = Literal["verified", "inferred", "uncertain", "failed"]


def resolve_conclusion(verdict: str, evidence_exists: bool) -> ConclusionState:
    """Map verdict + evidence presence to a 4-state user-facing conclusion.

    - verdict="pass" AND evidence_exists=True -> "verified"
    - verdict="pass" AND evidence_exists=False -> "inferred" (advisory: evidence gap)
    - verdict in ("insufficient", "pending", "action_required") -> "uncertain"
    - verdict in ("fail", "block") -> "failed"
    """
    normalized = str(verdict).strip().lower()
    if normalized == "pass":
        return "verified" if evidence_exists else "inferred"
    if normalized in ("insufficient", "pending", "action_required"):
        return "uncertain"
    # "fail", "block", "blocked", "error", or any other unknown -> "failed"
    return "failed"


class VerdictReceipt(TypedDict):
    status: VerdictStatus
    verdict: VerdictStatus
    blockers: list[str]
    planned_actions: list[Any]
    executed_actions: list[Any]
    provenance: str | None
    evidence_paths: dict[str, str]
    next_steps: list[str]
    executed: bool
    metadata: dict[str, Any]


_STATUS_ALIASES: dict[str, VerdictStatus] = {
    "pass": "pass",
    "passed": "pass",
    "ok": "pass",
    "success": "pass",
    "approved": "pass",
    "fail": "fail",
    "failed": "fail",
    "error": "fail",
    "reject": "fail",
    "rejected": "fail",
    "block": "fail",
    "blocked": "fail",
    "action_required": "action_required",
    "action-required": "action_required",
    "needs_action": "action_required",
    "needs-action": "action_required",
    "required": "action_required",
    "warn": "action_required",
    "warning": "action_required",
    "pending": "pending",
    "unknown": "pending",
    "inconclusive": "pending",
}


def _as_status(value: Any) -> VerdictStatus:
    text = str(value).strip().lower()
    return _STATUS_ALIASES.get(text, "pending")


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _as_dict_of_str(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, item in value.items():
        name = str(key).strip()
        text = str(item).strip()
        if name and text:
            normalized[name] = text
    return normalized


def normalize_verdict(raw: dict[str, Any]) -> VerdictReceipt:
    payload = raw if isinstance(raw, dict) else {}
    status = _as_status(payload.get("status", payload.get("verdict", "pending")))
    blockers = _as_str_list(payload.get("blockers"))
    if not blockers:
        blockers = _as_str_list(payload.get("unresolved_risks"))
    if not blockers:
        blockers = _as_str_list(payload.get("evidence_gaps"))

    planned_actions = _as_list(payload.get("planned_actions"))
    if not planned_actions:
        planned_actions = _as_list(payload.get("actions"))

    executed_actions = _as_list(payload.get("executed_actions"))
    if not executed_actions:
        executed_actions = _as_list(payload.get("fix_receipts"))

    next_steps = _as_str_list(payload.get("next_steps"))
    if not next_steps:
        next_steps = _as_str_list(payload.get("actions"))

    provenance_value = payload.get("provenance", payload.get("source"))
    provenance = str(provenance_value).strip() if provenance_value is not None else None
    if provenance == "":
        provenance = None

    evidence_paths = _as_dict_of_str(payload.get("evidence_paths"))
    metadata = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), dict) else {}

    known_fields = {
        "status",
        "verdict",
        "blockers",
        "planned_actions",
        "executed_actions",
        "provenance",
        "source",
        "evidence_paths",
        "next_steps",
        "executed",
        "metadata",
        "unresolved_risks",
        "evidence_gaps",
        "actions",
        "fix_receipts",
    }
    for key, value in payload.items():
        if key not in known_fields and key not in metadata:
            metadata[key] = value

    executed = bool(payload.get("executed", False))
    return {
        "status": status,
        "verdict": status,
        "blockers": blockers,
        "planned_actions": planned_actions,
        "executed_actions": executed_actions,
        "provenance": provenance,
        "evidence_paths": evidence_paths,
        "next_steps": next_steps,
        "executed": executed,
        "metadata": metadata,
    }


def action_required_verdict(blockers: list[str], *, next_steps: list[str] | None = None) -> VerdictReceipt:
    return {
        "status": "action_required",
        "verdict": "action_required",
        "blockers": _as_str_list(blockers),
        "planned_actions": [],
        "executed_actions": [],
        "provenance": None,
        "evidence_paths": {},
        "next_steps": _as_str_list(next_steps or []),
        "executed": False,
        "metadata": {},
    }


def pass_verdict(*, evidence_paths: dict[str, str] | None = None) -> VerdictReceipt:
    return {
        "status": "pass",
        "verdict": "pass",
        "blockers": [],
        "planned_actions": [],
        "executed_actions": [],
        "provenance": None,
        "evidence_paths": _as_dict_of_str(evidence_paths),
        "next_steps": [],
        "executed": True,
        "metadata": {},
    }


def fail_verdict(blockers: list[str], *, evidence_paths: dict[str, str] | None = None) -> VerdictReceipt:
    return {
        "status": "fail",
        "verdict": "fail",
        "blockers": _as_str_list(blockers),
        "planned_actions": [],
        "executed_actions": [],
        "provenance": None,
        "evidence_paths": _as_dict_of_str(evidence_paths),
        "next_steps": [],
        "executed": False,
        "metadata": {},
    }


__all__ = [
    "ConclusionState",
    "VerdictReceipt",
    "VerdictStatus",
    "action_required_verdict",
    "fail_verdict",
    "normalize_verdict",
    "pass_verdict",
    "resolve_conclusion",
]
