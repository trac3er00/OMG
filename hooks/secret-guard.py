#!/usr/bin/env python3
"""PreToolUse Hook (Read/Write/Edit/MultiEdit): Secret File Guard (Enterprise)

Delegates file policy decisions to policy_engine.py.
"""
import json
import os
import sys
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from hooks._common import bootstrap_runtime_paths, setup_crash_handler, json_input, deny_decision, is_bypass_mode, get_project_dir

bootstrap_runtime_paths(__file__)

# Fail-closed: deny on crash (security hook)
setup_crash_handler("secret-guard", fail_closed=True)

try:
    from hooks.policy_engine import evaluate_file_access, load_allowlist, to_pretool_hook_output
    from hooks.secret_audit import log_secret_access
    from runtime.mutation_gate import check_mutation_allowed
except Exception as _import_err:
    print(f"OMG secret-guard: policy_engine import failed: {_import_err}", file=sys.stderr)
    deny_decision(f"OMG secret-guard crash: policy_engine import failed: {_import_err}. Denying for safety.")
    sys.exit(0)

data = json_input()

tool = data.get("tool_name", "")
if tool not in ("Read", "Write", "Edit", "MultiEdit"):
    sys.exit(0)

file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

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
        deny_reason = str(gate_result.get("reason", "mutation denied by test intent lock gate"))
        try:
            from runtime.evidence_narrator import format_block_explanation
            _sg_explanation = format_block_explanation(deny_reason, {"tool": tool})
            deny_reason = f"{deny_reason}: {_sg_explanation}"
        except Exception:
            try:
                print(f"[omg:warn] failed to format mutation block explanation: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass
        try:
            import json as _sg_json
            from datetime import datetime as _sg_dt, timezone as _sg_tz
            _sg_artifact_dir = os.path.join(get_project_dir(), ".omg", "state")
            os.makedirs(_sg_artifact_dir, exist_ok=True)
            with open(os.path.join(_sg_artifact_dir, "last-block-explanation.json"), "w", encoding="utf-8") as _sg_f:
                _sg_json.dump({
                    "reason_code": str(gate_result.get("reason", "mutation denied by test intent lock gate")),
                    "explanation": deny_reason,
                    "tool": tool,
                    "timestamp": _sg_dt.now(_sg_tz.utc).isoformat(),
                }, _sg_f, indent=2)
        except Exception:
            try:
                print(f"[omg:warn] failed to write last block explanation artifact: {sys.exc_info()[1]}", file=sys.stderr)
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
                print(f"[omg:warn] failed to log denied secret access decision: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass
        deny_decision(deny_reason)
        sys.exit(0)

allowlist = load_allowlist(get_project_dir())
decision = evaluate_file_access(tool, file_path, allowlist=allowlist)

# Audit log: record every secret access decision
try:
    log_secret_access(
        project_dir=get_project_dir(),
        tool=tool,
        file_path=file_path,
        decision=decision.action,
        reason=decision.reason,
        allowlisted=False,
    )
except Exception:
    try:
        print(f"[omg:warn] failed to write secret access audit log: {sys.exc_info()[1]}", file=sys.stderr)
    except Exception:
        pass

# In bypass-permission mode, only enforce hard denials (critical safety).
# Skip "ask" decisions so the user is not prompted for confirmation.
if is_bypass_mode(data) and decision.action != "deny":
    sys.exit(0)

out = to_pretool_hook_output(decision)
if out:
    json.dump(out, sys.stdout)

sys.exit(0)
