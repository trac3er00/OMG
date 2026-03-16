from __future__ import annotations

from typing import TypedDict

from runtime.verdict_schema import VerdictReceipt


class NarrativeResult(TypedDict):
    verdict_summary: str
    blockers_section: list[str]
    provenance_note: str | None
    evidence_paths_section: list[str]
    next_actions: list[str]


BLOCK_REASON_CATALOG: dict[str, dict] = {
    "no_active_test_intent_lock": {
        "summary": "No active test-intent lock found.",
        "explanation": "OMG requires a test-intent lock before allowing source mutations.",
        "next_actions": [
            "Create a test-intent lock with `omg_test_intent_lock action=lock`",
            "Or add `exemption=docs` for documentation-only changes",
        ],
    },
    "mutation_context_required": {
        "summary": "No active governance context for this mutation.",
        "explanation": "Start a governed work session or use `omg ship` to register your intent before mutating source files.",
        "next_actions": [
            "Start a governed work session",
            "Or use `omg ship` to register your intent",
        ],
    },
    "tdd_proof_chain_incomplete": {
        "summary": "TDD proof chain incomplete.",
        "explanation": "The current session has source writes but no matching test evidence.",
        "next_actions": [
            "Provide test results before completing the session",
        ],
    },
    "tool_plan_required": {
        "summary": "A tool plan is required for this run.",
        "explanation": "Use `omg_test_intent_lock action=lock` with a test plan before proceeding with mutations.",
        "next_actions": [
            "Create a test plan with `omg_test_intent_lock action=lock`",
        ],
    },
    "planning_gate": {
        "summary": "Planning gate active: there are pending checklist items from the current session.",
        "explanation": "Complete or dismiss the checklist before ending the session.",
        "next_actions": [
            "Review and complete pending checklist items",
            "Or dismiss items if no longer relevant",
        ],
    },
    "done_when_required": {
        "summary": "done_when criteria not satisfied.",
        "explanation": "The done_when contract for this run has not been met.",
        "next_actions": [
            "Provide evidence of completion",
        ],
    },
}


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


def narrate_block_reason(reason_code: str, context: dict) -> NarrativeResult:
    """
    Convert a governance block reason code into a NarrativeResult.
    
    Args:
        reason_code: The block reason code (e.g., 'no_active_test_intent_lock')
        context: Context dict for interpolation (e.g., {'tool': 'Bash'})
    
    Returns:
        NarrativeResult with summary, blockers, and next_actions populated
    """
    if reason_code in BLOCK_REASON_CATALOG:
        entry = BLOCK_REASON_CATALOG[reason_code]
        summary = entry.get("summary", "")
        explanation = entry.get("explanation", "")
        next_actions = list(entry.get("next_actions", []))
    else:
        # Fallback for unknown reason codes
        summary = f"Governance block: {reason_code}"
        explanation = "An unknown governance block has been triggered."
        next_actions = ["Review the block reason and consult documentation"]
    
    # Combine summary and explanation into the verdict_summary
    verdict_summary = f"{summary} {explanation}".strip()
    
    return {
        "verdict_summary": verdict_summary,
        "blockers_section": [reason_code],
        "provenance_note": None,
        "evidence_paths_section": [],
        "next_actions": next_actions,
    }


def format_block_explanation(reason_code: str, context: dict) -> str:
    """
    Format a block reason into a single human-readable string.
    
    Args:
        reason_code: The block reason code
        context: Context dict for interpolation
    
    Returns:
        A formatted string: "{summary} — {next_actions joined with '; '}"
    """
    narrative = narrate_block_reason(reason_code, context)
    summary = narrative["verdict_summary"]
    next_actions = narrative["next_actions"]
    
    if next_actions:
        actions_str = "; ".join(next_actions)
        return f"{summary} — {actions_str}"
    else:
        return summary
