#!/usr/bin/env python3
"""PreToolUse Hook (Read/Write/Edit/MultiEdit): Secret File Guard (Enterprise)

Delegates file policy decisions to policy_engine.py.
"""

import json
import os
import sys
from typing import Any
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from hooks._common import (
    bootstrap_runtime_paths,
    setup_crash_handler,
    json_input,
    deny_decision,
    is_bypass_mode,
    get_project_dir,
)

bootstrap_runtime_paths(__file__)

# Fail-closed: deny on crash (security hook)
setup_crash_handler("secret-guard", fail_closed=True)

try:
    from hooks.policy_engine import (
        evaluate_file_access,
        load_allowlist,
        to_pretool_hook_output,
    )
    from hooks.secret_audit import log_secret_access
    from runtime.mutation_gate import check_mutation_allowed
except Exception as _import_err:
    print(
        f"OMG secret-guard: policy_engine import failed: {_import_err}", file=sys.stderr
    )
    deny_decision(
        f"OMG secret-guard crash: policy_engine import failed: {_import_err}. Denying for safety."
    )
    sys.exit(0)


def _requires_bypass_enforcement(
    action: str, risk_level: str, controls: list[str]
) -> bool:
    normalized_controls = {
        str(control).strip().lower() for control in controls if str(control).strip()
    }
    if "deny-on-bypass" in normalized_controls:
        return True
    return action == "ask" and str(risk_level).strip().lower() in {"high", "critical"}


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input")

    normalized: dict[str, Any] = dict(payload)
    normalized["tool_name"] = payload.get("tool_name", payload.get("tool", ""))
    normalized["tool_input"] = tool_input if isinstance(tool_input, dict) else {}
    return normalized


def check_file_access(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = _normalize_payload(payload)

    tool = data.get("tool_name", "")
    if tool not in ("Read", "Write", "Edit", "MultiEdit"):
        return None

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None

    if tool in ("Write", "Edit", "MultiEdit"):
        tool_input = data.get("tool_input", {})
        metadata = tool_input.get("metadata") if isinstance(tool_input, dict) else None
        lock_id = tool_input.get("lock_id") if isinstance(tool_input, dict) else None
        if not isinstance(lock_id, str) and isinstance(metadata, dict):
            lock_id = metadata.get("lock_id")
        exemption = tool_input.get("exemption") if isinstance(tool_input, dict) else None

        gate_result = check_mutation_allowed(
            tool=tool,
            file_path=file_path,
            project_dir=get_project_dir(),
            lock_id=lock_id if isinstance(lock_id, str) else None,
            exemption=exemption if isinstance(exemption, str) else None,
        )
        if gate_result.get("status") == "blocked":
            deny_reason = str(
                gate_result.get("reason", "mutation denied by test intent lock gate")
            )
            try:
                from runtime.evidence_narrator import format_block_explanation

                _sg_explanation = format_block_explanation(deny_reason, {"tool": tool})
                deny_reason = f"{deny_reason}: {_sg_explanation}"
            except Exception:
                try:
                    print(
                        f"[omg:warn] failed to format mutation block explanation: {sys.exc_info()[1]}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
            try:
                import json as _sg_json
                from datetime import datetime as _sg_dt, timezone as _sg_tz

                _sg_artifact_dir = os.path.join(get_project_dir(), ".omg", "state")
                os.makedirs(_sg_artifact_dir, exist_ok=True)
                with open(
                    os.path.join(_sg_artifact_dir, "last-block-explanation.json"),
                    "w",
                    encoding="utf-8",
                ) as _sg_f:
                    _sg_json.dump(
                        {
                            "reason_code": str(
                                gate_result.get(
                                    "reason", "mutation denied by test intent lock gate"
                                )
                            ),
                            "explanation": deny_reason,
                            "tool": tool,
                            "timestamp": _sg_dt.now(_sg_tz.utc).isoformat(),
                        },
                        _sg_f,
                        indent=2,
                    )
            except Exception:
                try:
                    print(
                        f"[omg:warn] failed to write last block explanation artifact: {sys.exc_info()[1]}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
            try:
                log_secret_access(
                    project_dir=get_project_dir(),
                    tool=tool,
                    file_path=file_path,
                    decision="deny",
                    reason=deny_reason,
                    allowlisted=False,
                )
            except Exception:
                try:
                    print(
                        f"[omg:warn] failed to log denied secret access decision: {sys.exc_info()[1]}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
            return deny_decision(deny_reason)

    allowlist = load_allowlist(get_project_dir())
    decision = evaluate_file_access(tool, file_path, allowlist=allowlist)

    try:
        allowlisted = decision.reason.startswith("Allowlisted:")
        log_secret_access(
            project_dir=get_project_dir(),
            tool=tool,
            file_path=file_path,
            decision=decision.action,
            reason=decision.reason,
            allowlisted=allowlisted,
        )
    except Exception:
        try:
            print(
                f"[omg:warn] failed to write secret access audit log: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    if is_bypass_mode(data) and decision.action != "deny":
        if _requires_bypass_enforcement(
            decision.action,
            decision.risk_level,
            decision.controls or [],
        ):
            return deny_decision(f"Blocked in bypass mode: {decision.reason}")
        return None

    return to_pretool_hook_output(decision)


def main() -> None:
    out = check_file_access(json_input())
    if out:
        json.dump(out, sys.stdout)

    sys.exit(0)


if __name__ == "__main__":
    main()
