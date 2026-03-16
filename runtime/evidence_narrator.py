from __future__ import annotations

from typing import TypedDict

from runtime.verdict_schema import VerdictReceipt


class NarrativeResult(TypedDict):
    verdict_summary: str
    blockers_section: list[str]
    provenance_note: str | None
    evidence_paths_section: list[str]
    next_actions: list[str]


def narrate(verdict: VerdictReceipt) -> NarrativeResult:
    status = verdict.get("status", "pending")
    
    if status == "pass":
        summary = "The verification process passed successfully."
    elif status == "fail":
        summary = "The verification process failed."
    elif status == "action_required":
        summary = "Action required to complete the verification process."
    else:
        summary = "The verification process is pending or in an unknown state."

    blockers = list(verdict.get("blockers", []))
    next_steps = list(verdict.get("next_steps", []))
    
    evidence_paths = verdict.get("evidence_paths", {})
    evidence_sections = [f"{k}: {v}" for k, v in evidence_paths.items()]
    
    provenance = verdict.get("provenance")
    
    return {
        "verdict_summary": summary,
        "blockers_section": blockers,
        "provenance_note": provenance,
        "evidence_paths_section": evidence_sections,
        "next_actions": next_steps,
    }
