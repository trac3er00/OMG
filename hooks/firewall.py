#!/usr/bin/env python3
"""PreToolUse Hook (Bash): Command Firewall (Enterprise)

Delegates policy logic to policy_engine.py so all command decisions are driven by
one centralized decision model.
"""
import json
import os
import sys
from pathlib import Path

HOOKS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(HOOKS_DIR)
for path in (HOOKS_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from _common import setup_crash_handler, json_input, deny_decision, is_bypass_mode, get_project_dir  # pyright: ignore[reportImplicitRelativeImport]

# Fail-closed: deny on crash (security hook)
setup_crash_handler("firewall", fail_closed=True)

try:
    from policy_engine import evaluate_bash_command, to_pretool_hook_output  # pyright: ignore[reportImplicitRelativeImport]
    from runtime.mutation_gate import check_mutation_allowed
    from runtime.tool_plan_gate import journal_mutation_bash
except Exception as _import_err:
    print(f"OMG firewall: policy_engine import failed: {_import_err}", file=sys.stderr)
    deny_decision(f"OMG firewall crash: policy_engine import failed: {_import_err}. Denying for safety.")
    sys.exit(0)


def _enrich_risk_context(decision, payload: dict[str, object]):
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        run_id = _resolve_run_id(payload)

        suffixes: list[str] = []
        defense_risk = _read_defense_risk(project_dir)
        if defense_risk:
            suffixes.append(f"defense risk={defense_risk}")

        council_signal = _read_council_signal(project_dir, run_id)
        if council_signal:
            suffixes.append(council_signal)

        if suffixes:
            decision.reason = f"{decision.reason} [{'; '.join(suffixes)}]".strip()
    except Exception:
        return decision
    return decision


def _resolve_run_id(payload: dict[str, object]) -> str:
    if isinstance(payload, dict):
        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id.strip()
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            metadata = tool_input.get("metadata")
            if isinstance(metadata, dict):
                metadata_run_id = metadata.get("run_id")
                if isinstance(metadata_run_id, str) and metadata_run_id.strip():
                    return metadata_run_id.strip()
    env_run_id = os.environ.get("OMG_RUN_ID", "")
    return env_run_id.strip()


def _read_defense_risk(project_dir: str) -> str:
    path = Path(project_dir) / ".omg" / "state" / "defense_state" / "current.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("risk_level", "")).strip().lower()


def _read_council_signal(project_dir: str, run_id: str) -> str:
    if not run_id:
        return ""
    path = Path(project_dir) / ".omg" / "state" / "council_verdicts" / f"{run_id}.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""

    verdicts = payload.get("verdicts")
    if not isinstance(verdicts, dict):
        return ""
    evidence = verdicts.get("evidence_completeness")
    if not isinstance(evidence, dict):
        return ""
    verdict = str(evidence.get("verdict", "")).strip().lower()
    findings = evidence.get("findings")
    findings_count = len(findings) if isinstance(findings, list) else 0
    if not verdict:
        return ""
    return f"council evidence={verdict} findings={findings_count}"


def _read_clarification_state(project_dir: str, run_id: str) -> dict[str, object]:
    if not run_id:
        return {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        }
    path = Path(project_dir) / ".omg" / "state" / "intent_gate" / f"{run_id}.json"
    if not path.exists():
        return {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        }
    if not isinstance(payload, dict):
        return {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        }
    prompt = " ".join(str(payload.get("clarification_prompt", "")).split())
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "requires_clarification": bool(payload.get("requires_clarification") is True),
        "intent_class": str(payload.get("intent_class", "")).strip(),
        "clarification_prompt": prompt,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }


def _clarification_reason(clarification_prompt: str) -> str:
    prompt = " ".join(str(clarification_prompt or "").split())
    if prompt:
        return f"Clarification required before mutation: {prompt}"
    return "Clarification required before mutation: provide the missing intent details."

data = json_input()

tool = data.get("tool_name", "")
if tool != "Bash":
    sys.exit(0)

cmd = data.get("tool_input", {}).get("command", "")
if not cmd:
    sys.exit(0)

decision = evaluate_bash_command(cmd)
decision = _enrich_risk_context(decision, data)

tool_input = data.get("tool_input")
metadata = tool_input.get("metadata") if isinstance(tool_input, dict) else None
lock_id = tool_input.get("lock_id") if isinstance(tool_input, dict) else None
if not isinstance(lock_id, str) and isinstance(metadata, dict):
    lock_id = metadata.get("lock_id")
run_id = _resolve_run_id(data)

gate_result = check_mutation_allowed(
    tool="Bash",
    file_path=cmd,
    project_dir=get_project_dir(),
    lock_id=lock_id if isinstance(lock_id, str) else None,
    command=cmd,
    run_id=run_id or None,
    metadata=metadata if isinstance(metadata, dict) else None,
)
is_mutation_capable = str(gate_result.get("reason", "")) != "tool is read-only for mutation gate"
clarification_state = _read_clarification_state(get_project_dir(), run_id)
if clarification_state.get("requires_clarification") is True and is_mutation_capable:
    deny_decision(_clarification_reason(str(clarification_state.get("clarification_prompt", ""))))
    sys.exit(0)

if is_mutation_capable and gate_result.get("status") == "blocked":
    deny_decision(str(gate_result.get("reason", "mutation denied by test intent lock gate")))
    sys.exit(0)

# In bypass-permission mode, only enforce hard denials (critical safety).
# Skip "ask" decisions so the user is not prompted for confirmation.
if is_bypass_mode(data) and decision.action != "deny":
    sys.exit(0)

if decision.action == "allow" and is_mutation_capable:
    try:
        journal_mutation_bash(
            project_dir=get_project_dir(),
            command=cmd,
            run_id=run_id or None,
            metadata=metadata if isinstance(metadata, dict) else None,
        )
    except Exception:
        pass

out = to_pretool_hook_output(decision)
if out:
    json.dump(out, sys.stdout)

sys.exit(0)
