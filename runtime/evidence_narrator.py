from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NotRequired, TypedDict

from runtime.verdict_schema import ConclusionState, VerdictReceipt


# Patterns that indicate completion claims requiring proof
COMPLETION_CLAIM_PATTERNS: list[str] = [
    r"\b(done|fixed|works|ready|shipped|completed|lgtm)\b",
    r"\btests?\s+(pass|passed|passing|green)\b",
]


class CompletionClaimValidity(TypedDict):
    allowed: bool
    reason: str
    missing: list[str]
    conclusion: ConclusionState
    advisory: NotRequired[str]


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


def check_completion_claim_validity(project_dir: str) -> CompletionClaimValidity:
    """Check if a completion claim (done/works/ready) is supported by evidence.

    Args:
        project_dir: Path to the project root directory.

    Returns:
        CompletionClaimValidity dict with:
        - allowed: True if claim is allowed (no active session OR passing proof exists)
        - reason: Human-readable explanation
        - missing: List of missing evidence items
        - conclusion: ConclusionState from verdict_schema
    """
    root = Path(project_dir)
    session_path = root / ".omg" / "state" / "session.json"
    evidence_dir = root / ".omg" / "evidence"
    missing: list[str] = []

    # Check for active session via session.json
    active_run_id: str | None = None
    if session_path.exists():
        try:
            session_data = json.loads(session_path.read_text(encoding="utf-8"))
            active_run_id = str(session_data.get("run_id", "")).strip() or None
        except (OSError, json.JSONDecodeError):
            pass

    # No active session means no active work requiring proof
    if not active_run_id:
        return {
            "allowed": True,
            "reason": "No active session requiring proof",
            "missing": [],
            "conclusion": "verified",
        }

    # Active session exists - check for proof gate verdict
    proof_verdict_path = root / ".omg" / "state" / "proof_gate" / f"{active_run_id}.json"
    has_passing_proof = False
    if proof_verdict_path.exists():
        try:
            proof_data = json.loads(proof_verdict_path.read_text(encoding="utf-8"))
            verdict = str(proof_data.get("verdict", "")).strip().lower()
            has_passing_proof = verdict == "pass"
        except (OSError, json.JSONDecodeError):
            pass

    if not has_passing_proof:
        missing.append("proof gate verdict")

    # Check for evidence bundle
    has_evidence_bundle = False
    if evidence_dir.exists():
        # Look for any evidence file matching the run_id
        evidence_patterns = [
            f"*{active_run_id}*.json",
            "junit*.xml",
            "coverage*.xml",
            "*.sarif",
        ]
        for pattern in evidence_patterns:
            if list(evidence_dir.glob(pattern)):
                has_evidence_bundle = True
                break

    if not has_evidence_bundle:
        missing.append("evidence bundle")

    # Determine conclusion based on what's present
    if has_passing_proof and has_evidence_bundle:
        return {
            "allowed": True,
            "reason": "Proof gate passed with evidence",
            "missing": [],
            "conclusion": "verified",
        }
    elif has_passing_proof:
        return {
            "allowed": True,
            "reason": "Proof gate passed (evidence inferred — collect evidence to upgrade to verified)",
            "missing": missing,
            "conclusion": "inferred",
            "advisory": "Evidence bundle missing. Run verification commands to produce machine-readable evidence.",
        }
    elif missing:
        return {
            "allowed": False,
            "reason": "Active session lacks proof",
            "missing": missing,
            "conclusion": "uncertain",
        }
    else:
        return {
            "allowed": False,
            "reason": "Cannot verify completion",
            "missing": ["test results", "proof gate verdict"],
            "conclusion": "failed",
        }


def narrate_missing_evidence(missing: list[str]) -> str:
    """Convert missing evidence items into a human-readable message.

    Args:
        missing: List of missing evidence item names.

    Returns:
        Human-readable message explaining what's missing.

    Example:
        >>> narrate_missing_evidence(["test results", "proof gate verdict"])
        "Cannot confirm 'done' - missing: test results, proof gate verdict"
    """
    if not missing:
        return "All required evidence is present."

    items_str = ", ".join(missing)
    return f"Cannot confirm 'done' - missing: {items_str}"


def matches_completion_claim(text: str) -> bool:
    """Check if text contains completion claim keywords.

    Args:
        text: Text to check for completion claims.

    Returns:
        True if text matches any COMPLETION_CLAIM_PATTERNS.
    """
    text_lower = text.lower()
    for pattern in COMPLETION_CLAIM_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False
