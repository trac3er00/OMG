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

from _common import setup_crash_handler, json_input, deny_decision, is_bypass_mode

# Fail-closed: deny on crash (security hook)
setup_crash_handler("secret-guard", fail_closed=True)

try:
    from policy_engine import evaluate_file_access, to_pretool_hook_output
except Exception as _import_err:
    print(f"OAL secret-guard: policy_engine import failed: {_import_err}", file=sys.stderr)
    deny_decision(f"OAL secret-guard crash: policy_engine import failed: {_import_err}. Denying for safety.")
    sys.exit(0)

data = json_input()

tool = data.get("tool_name", "")
if tool not in ("Read", "Write", "Edit", "MultiEdit"):
    sys.exit(0)

file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

decision = evaluate_file_access(tool, file_path)

# In bypass-permission mode, only enforce hard denials (critical safety).
# Skip "ask" decisions so the user is not prompted for confirmation.
if is_bypass_mode(data) and decision.action != "deny":
    sys.exit(0)

out = to_pretool_hook_output(decision)
if out:
    json.dump(out, sys.stdout)

sys.exit(0)
