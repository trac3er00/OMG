#!/usr/bin/env python3
"""PreToolUse Hook (Read/Write/Edit/MultiEdit): Secret File Guard (Enterprise)

Delegates file policy decisions to policy_engine.py.
"""
import json
import os
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, deny_decision, is_bypass_mode, is_bypass_all, is_accept_edits_mode, is_plan_mode, get_project_dir

# Fail-closed: deny on crash (security hook)
setup_crash_handler("secret-guard", fail_closed=True)

try:
    from policy_engine import evaluate_file_access, to_pretool_hook_output
    from secret_audit import log_secret_access
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

decision = evaluate_file_access(tool, file_path)

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
    pass  # Crash isolation: audit logging must never break the hook

# plan mode: deny ALL write operations (plan = read-only)
if is_plan_mode(data) and tool in ("Write", "Edit", "MultiEdit"):
    deny_decision("Plan mode: write operations blocked. Switch to implement mode to make changes.")
    sys.exit(0)

# In bypass-permission mode, only enforce hard denials (critical safety).
# Skip "ask" decisions so the user is not prompted for confirmation.
if is_bypass_mode(data) and decision.action != "deny":
    sys.exit(0)

# bypass_all flag: same behavior as bypassPermissions
if is_bypass_all(data) and decision.action != "deny":
    sys.exit(0)

# acceptEdits mode: skip ask decisions for file edits (but NOT secret file denials)
if is_accept_edits_mode(data) and decision.action == "ask":
    sys.exit(0)

out = to_pretool_hook_output(decision)
if out:
    json.dump(out, sys.stdout)

sys.exit(0)
