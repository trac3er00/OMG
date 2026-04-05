#!/usr/bin/env python3
"""OMG v1 Terminal Approval UI — governance gate approval requests in terminal.

Modes: interactive (TTY prompt), non-interactive (auto-deny), batch (pre-approval).
Decisions logged+signed to .omg/state/ledger/approvals.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "green": "\033[92m",
    "cyan": "\033[96m",
    "dim": "\033[2m",
}

_RISK_COLORS = {
    "critical": "red",
    "high": "red",
    "med": "yellow",
    "low": "green",
}

_APPROVAL_LEDGER_PATH = os.path.join(".omg", "state", "ledger", "approvals.jsonl")
_PREAPPROVALS_PATH = os.path.join(".omg", "state", "ralph-approvals.json")


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False


def _c(name: str) -> str:
    if not _supports_color():
        return ""
    return _COLORS.get(name, "")


def _risk_color(level: str) -> str:
    return _c(_RISK_COLORS.get(level, "dim"))


def _is_interactive() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _load_preapprovals(project_dir: str) -> dict[str, Any]:
    path = os.path.join(project_dir, _PREAPPROVALS_PATH)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _check_preapproval(
    project_dir: str,
    action: str,
    risk_level: str,
) -> str | None:
    approvals = _load_preapprovals(project_dir)

    if approvals.get("allow_all"):
        return "preapproved_all"

    approved_risk_levels = approvals.get("approved_risk_levels")
    if isinstance(approved_risk_levels, list) and risk_level in approved_risk_levels:
        return "preapproved_risk_level"

    approved_actions = approvals.get("approved_actions")
    if isinstance(approved_actions, (list, set)):
        if action in approved_actions:
            return "preapproved_action"

    return None


def _format_approval_request(
    action: str,
    risk_level: str,
    reasons: list[str],
    controls: list[str],
    alternatives: list[str] | None = None,
) -> str:
    bold = _c("bold")
    reset = _c("reset")
    dim = _c("dim")
    cyan = _c("cyan")
    rc = _risk_color(risk_level)

    lines: list[str] = []
    lines.append("")
    lines.append(f"{bold}{'=' * 60}{reset}")
    lines.append(f"{bold}  OMG Governance Gate — Approval Required{reset}")
    lines.append(f"{bold}{'=' * 60}{reset}")
    lines.append("")

    lines.append(f"  {bold}Action:{reset}     {action}")
    lines.append(f"  {bold}Risk Level:{reset} {rc}{risk_level.upper()}{reset}")
    lines.append("")

    if reasons:
        lines.append(f"  {bold}Reasons:{reset}")
        for reason in reasons[:8]:
            lines.append(f"    {dim}\u2022{reset} {reason}")
        lines.append("")

    if controls:
        lines.append(f"  {bold}Required Controls:{reset}")
        for control in controls[:6]:
            lines.append(f"    {cyan}\u25b8{reset} {control}")
        lines.append("")

    if alternatives:
        lines.append(f"  {bold}Suggested Alternatives:{reset}")
        for alt in alternatives[:4]:
            lines.append(f"    {dim}\u2192{reset} {alt}")
        lines.append("")

    lines.append(f"  {bold}Options:{reset}")
    lines.append(
        f"    {_c('green')}[a]{reset} Approve              \u2014 allow this action"
    )
    lines.append(
        f"    {_c('red')}[d]{reset} Deny                 \u2014 block this action"
    )
    lines.append(
        f"    {_c('green')}[A]{reset} Approve All Similar  \u2014 approve all at this risk level"
    )
    lines.append(
        f"    {_c('red')}[D]{reset} Deny All Similar     \u2014 deny all at this risk level"
    )
    lines.append("")
    lines.append(f"{bold}{'-' * 60}{reset}")

    return "\n".join(lines)


def _sign_approval_record(record: dict[str, Any]) -> str:
    """SHA-256 integrity digest over the approval record (security-critical)."""
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def log_approval_decision(
    project_dir: str,
    action: str,
    decision: str,
    risk_level: str,
    mode: str,
    reasons: list[str] | None = None,
    controls: list[str] | None = None,
) -> None:
    """Append signed approval record to .omg/state/ledger/approvals.jsonl."""
    ledger_path = os.path.join(project_dir, _APPROVAL_LEDGER_PATH)
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "decision": decision,
        "risk_level": risk_level,
        "mode": mode,
        "reasons": reasons or [],
        "controls": controls or [],
    }
    record["digest"] = _sign_approval_record(record)

    try:
        with open(ledger_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        try:
            print(
                f"[omg:warn] [approval_ui] failed to log approval decision: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass


def present_approval_request(
    action: str,
    risk_level: str,
    reasons: list[str] | None = None,
    controls: list[str] | None = None,
    alternatives: list[str] | None = None,
    project_dir: str = ".",
    *,
    _input_fn: Any = None,
) -> str:
    """Present governance approval request. Returns "approve"/"deny"/"approve_all"/"deny_all".

    Resolution order: pre-approval file -> interactive TTY prompt -> auto-deny.
    _input_fn overrides input() for testing.
    """
    reasons = reasons or []
    controls = controls or []

    preapproval_mode = _check_preapproval(project_dir, action, risk_level)
    if preapproval_mode:
        log_approval_decision(
            project_dir=project_dir,
            action=action,
            decision="approve",
            risk_level=risk_level,
            mode=preapproval_mode,
            reasons=reasons,
            controls=controls,
        )
        return "approve"

    if not _is_interactive() and _input_fn is None:
        log_approval_decision(
            project_dir=project_dir,
            action=action,
            decision="deny",
            risk_level=risk_level,
            mode="auto_deny_non_interactive",
            reasons=reasons,
            controls=controls,
        )
        return "deny"

    display = _format_approval_request(
        action=action,
        risk_level=risk_level,
        reasons=reasons,
        controls=controls,
        alternatives=alternatives,
    )
    print(display, file=sys.stderr)

    prompt_fn = _input_fn if _input_fn is not None else input
    try:
        response = prompt_fn("  Decision [a/d/A/D]: ").strip()
    except (EOFError, KeyboardInterrupt):
        response = ""

    decision_map = {
        "a": "approve",
        "approve": "approve",
        "y": "approve",
        "yes": "approve",
        "d": "deny",
        "deny": "deny",
        "n": "deny",
        "no": "deny",
        "A": "approve_all",
        "D": "deny_all",
    }
    decision = decision_map.get(response, "deny")

    mode = "cli_interactive"
    if decision in ("approve_all", "deny_all"):
        mode = f"cli_interactive_batch_{decision}"

    log_approval_decision(
        project_dir=project_dir,
        action=action,
        decision=decision,
        risk_level=risk_level,
        mode=mode,
        reasons=reasons,
        controls=controls,
    )

    return decision


def resolve_governance_ask(
    review: dict[str, Any],
    project_dir: str = ".",
    *,
    _input_fn: Any = None,
) -> dict[str, Any]:
    """Resolve 'ask' verdict from trust review via terminal approval UI.

    Returns the review dict with verdict updated and 'approval_resolution' added.
    Non-'ask' verdicts pass through unchanged.
    """
    verdict = review.get("verdict", "allow")
    if verdict != "ask":
        return review

    action_desc = _build_action_description(review)
    risk_level = review.get("risk_level", "med")
    reasons = review.get("reasons", [])
    controls = review.get("controls", [])

    decision = present_approval_request(
        action=action_desc,
        risk_level=risk_level,
        reasons=reasons,
        controls=controls,
        project_dir=project_dir,
        _input_fn=_input_fn,
    )

    resolved_verdict = "allow" if decision in ("approve", "approve_all") else "deny"

    review["approval_resolution"] = {
        "original_verdict": "ask",
        "user_decision": decision,
        "resolved_verdict": resolved_verdict,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    review["verdict"] = resolved_verdict

    return review


def _build_action_description(review: dict[str, Any]) -> str:
    parts: list[str] = []

    changed_files = review.get("changed_files", [])
    if changed_files:
        parts.append(f"Config change in: {', '.join(changed_files)}")

    mcp_changes = review.get("mcp_changes", [])
    for change in mcp_changes[:3]:
        ctype = change.get("type", "unknown")
        server = change.get("server", "unknown")
        parts.append(f"MCP server {ctype}: {server}")

    hook_changes = review.get("hook_changes", {})
    added_events = hook_changes.get("added_events", [])
    removed_events = hook_changes.get("removed_events", [])
    if added_events:
        parts.append(f"Hook events added: {', '.join(added_events)}")
    if removed_events:
        parts.append(f"Hook events removed: {', '.join(removed_events)}")

    env_changes = review.get("env_changes", [])
    if env_changes:
        keys = [str(c.get("key", "")) for c in env_changes[:3]]
        parts.append(f"Env vars changed: {', '.join(keys)}")

    if not parts:
        reasons = review.get("reasons", [])
        if reasons:
            parts.append(reasons[0])
        else:
            parts.append("Configuration change requiring approval")

    return "; ".join(parts)
