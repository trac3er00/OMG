#!/usr/bin/env python3
"""PreToolUse Hook (Bash): Command Firewall (Enterprise)

Delegates policy logic to policy_engine.py so all command decisions are driven by
one centralized decision model.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from _common import bootstrap_runtime_paths, setup_crash_handler, json_input, deny_decision, is_bypass_mode, get_project_dir  # pyright: ignore[reportImplicitRelativeImport]
from security_validators import sanitize_run_id  # pyright: ignore[reportImplicitRelativeImport]

bootstrap_runtime_paths(__file__)

# Fail-closed: deny on crash (security hook)
setup_crash_handler("firewall", fail_closed=True)

try:
    from policy_engine import evaluate_bash_command, to_pretool_hook_output, scan_mutation_command, ask, deny  # pyright: ignore[reportImplicitRelativeImport]
    from runtime.compliance_governor import classify_bash_command_mode
    from runtime.context_engine import _extract_clarification
    from runtime.defense_state import DefenseState
    from runtime.session_health import compute_session_health
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
            return sanitize_run_id(run_id)
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            metadata = tool_input.get("metadata")
            if isinstance(metadata, dict):
                metadata_run_id = metadata.get("run_id")
                if isinstance(metadata_run_id, str) and metadata_run_id.strip():
                    return sanitize_run_id(metadata_run_id)
    env_run_id = os.environ.get("OMG_RUN_ID", "")
    return sanitize_run_id(env_run_id) if env_run_id.strip() else ""


def _resolve_active_run_id(project_dir: str) -> str:
    active_run_path = Path(project_dir) / ".omg" / "shadow" / "active-run"
    if not active_run_path.exists():
        return ""
    try:
        return active_run_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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
        return _extract_clarification({})
    path = Path(project_dir) / ".omg" / "state" / "intent_gate" / f"{run_id}.json"
    if not path.exists():
        return _extract_clarification({})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _extract_clarification({})
    if not isinstance(payload, dict):
        return _extract_clarification({})
    return _extract_clarification(payload)


def _clarification_reason(clarification_prompt: str) -> str:
    prompt = " ".join(str(clarification_prompt or "").split())
    if prompt:
        return f"Clarification required before mutation: {prompt}"
    return "Clarification required before mutation: provide the missing intent details."


def _clarification_external_reason(clarification_prompt: str) -> str:
    prompt = " ".join(str(clarification_prompt or "").split())
    if prompt:
        return f"Clarification required before external execution: {prompt}"
    return "Clarification required before external execution: provide the missing intent details."


def _strict_ambiguity_mode_enabled() -> bool:
    token = str(os.environ.get("OMG_STRICT_AMBIGUITY_MODE", "1")).strip().lower()
    return token not in {"0", "false", "off", "no"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mutating_defense_decision(
    *,
    project_dir: str,
    cmd: str,
    run_id: str,
):
    scan = scan_mutation_command(cmd)
    defense_state = DefenseState(project_dir).update(
        injection_hits=int(_to_float(scan.get("injection_hits"), 0.0)),
        contamination_score=_to_float(scan.get("contamination_score"), 0.0),
        overthinking_score=_to_float(scan.get("overthinking_score"), 0.0),
        premature_fixer_score=_to_float(scan.get("premature_fixer_score"), 0.0),
    )

    resolved_run_id = run_id.strip() or _resolve_active_run_id(project_dir) or "default"
    session_health = compute_session_health(project_dir, run_id=resolved_run_id)

    contamination = _to_float(session_health.get("contamination_risk"), _to_float(defense_state.get("contamination_score"), 0.0))
    overthinking = _to_float(session_health.get("overthinking_score"), _to_float(defense_state.get("overthinking_score"), 0.0))
    premature_fixer = _to_float(defense_state.get("premature_fixer_score"), 0.0)
    health_action = str(session_health.get("recommended_action", "continue"))
    thresholds = session_health.get("thresholds") if isinstance(session_health, dict) else {}
    contamination_thresholds = thresholds.get("contamination_risk") if isinstance(thresholds, dict) else {}
    overthinking_thresholds = thresholds.get("overthinking_score") if isinstance(thresholds, dict) else {}
    reflect_contamination = _to_float(contamination_thresholds.get("reflect") if isinstance(contamination_thresholds, dict) else None, 0.05)
    reflect_overthinking = _to_float(overthinking_thresholds.get("reflect") if isinstance(overthinking_thresholds, dict) else None, 0.15)
    reflect_triggers = session_health.get("reflect_triggers") if isinstance(session_health, dict) else {}
    contamination_trigger = bool(reflect_triggers.get("contamination")) if isinstance(reflect_triggers, dict) else contamination > reflect_contamination
    overthinking_trigger = bool(reflect_triggers.get("overthinking")) if isinstance(reflect_triggers, dict) else overthinking > reflect_overthinking
    pause_required = bool(session_health.get("defense_pause_required") is True) if isinstance(session_health, dict) else (contamination_trigger or overthinking_trigger)
    signal_text = ", ".join(str(item) for item in scan.get("signals", []) if str(item)) or "none"
    context = (
        f"defense hits={int(_to_float(defense_state.get('injection_hits'), 0.0))} "
        f"contamination={contamination:.4f} overthinking={overthinking:.4f} "
        f"premature_fixer={premature_fixer:.4f} "
        f"session_health={health_action} signals={signal_text}"
    )

    if health_action == "block":
        return deny(
            f"Blocked: mutation denied by defense/session-health reducer [{context}]",
            "high",
            ["defense-reducer", "session-health"],
        )

    if pause_required or contamination_trigger or overthinking_trigger:
        return ask(
            "Pause: mutation requires reflection before execution "
            f"[{context}; thresholds contamination>{reflect_contamination:.2f} "
            f"overthinking>{reflect_overthinking:.2f}]",
            "high",
            ["reflect", "defense-reducer", "session-health"],
        )

    return None

data = json_input()

tool = data.get("tool_name", "")
if tool != "Bash":
    sys.exit(0)

cmd = data.get("tool_input", {}).get("command", "")
if not cmd:
    sys.exit(0)

decision = evaluate_bash_command(cmd)

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
bash_mode = classify_bash_command_mode(cmd)
is_mutation_capable = bash_mode == "mutation"
is_external_execution = bash_mode == "external"
clarification_state = _read_clarification_state(get_project_dir(), run_id)
strict_ambiguity_mode = _strict_ambiguity_mode_enabled()
if is_mutation_capable:
    defense_decision = _mutating_defense_decision(
        project_dir=get_project_dir(),
        cmd=cmd,
        run_id=run_id,
    )
    if defense_decision is not None:
        decision = defense_decision

if strict_ambiguity_mode and clarification_state.get("requires_clarification") is True and (is_mutation_capable or is_external_execution):
    prompt = str(clarification_state.get("clarification_prompt", ""))
    if is_external_execution:
        deny_decision(_clarification_external_reason(prompt))
    else:
        deny_decision(_clarification_reason(prompt))
    sys.exit(0)

if is_mutation_capable and gate_result.get("status") == "blocked":
    _fw_reason_code = str(gate_result.get("reason", "mutation denied by test intent lock gate"))
    try:
        from runtime.evidence_narrator import format_block_explanation
        _fw_explanation = format_block_explanation(_fw_reason_code, {"tool": tool})
        _fw_enhanced_reason = f"{_fw_reason_code}: {_fw_explanation}"
    except Exception:
        _fw_enhanced_reason = _fw_reason_code  # Crash isolation: always falls back
    try:
        import json as _fw_json
        from datetime import datetime as _fw_dt, timezone as _fw_tz
        _fw_artifact_dir = os.path.join(get_project_dir(), ".omg", "state")
        os.makedirs(_fw_artifact_dir, exist_ok=True)
        with open(os.path.join(_fw_artifact_dir, "last-block-explanation.json"), "w", encoding="utf-8") as _fw_f:
            _fw_json.dump({
                "reason_code": _fw_reason_code,
                "explanation": _fw_enhanced_reason,
                "tool": tool,
                "timestamp": _fw_dt.now(_fw_tz.utc).isoformat(),
            }, _fw_f, indent=2)
    except Exception:
        pass  # Best-effort only
    deny_decision(_fw_enhanced_reason)
    sys.exit(0)

decision = _enrich_risk_context(decision, data)

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
