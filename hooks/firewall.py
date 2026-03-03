#!/usr/bin/env python3
"""PreToolUse Hook (Bash): Command Firewall (Enterprise)

Delegates policy logic to policy_engine.py so all command decisions are driven by
one centralized decision model.
"""
import json
import os
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, deny_decision, is_bypass_mode

# Fail-closed: deny on crash (security hook)
setup_crash_handler("firewall", fail_closed=True)

try:
    from policy_engine import evaluate_bash_command, to_pretool_hook_output
except Exception as _import_err:
    print(f"OMG firewall: policy_engine import failed: {_import_err}", file=sys.stderr)
    deny_decision(f"OMG firewall crash: policy_engine import failed: {_import_err}. Denying for safety.")
    sys.exit(0)

data = json_input()

tool = data.get("tool_name", "")
if tool != "Bash":
    sys.exit(0)

cmd = data.get("tool_input", {}).get("command", "")
if not cmd:
    sys.exit(0)

decision = evaluate_bash_command(cmd)

# In bypass-permission mode, only enforce hard denials (critical safety).
# Skip "ask" decisions so the user is not prompted for confirmation.
if is_bypass_mode(data) and decision.action != "deny":
    sys.exit(0)

out = to_pretool_hook_output(decision)
if out:
    json.dump(out, sys.stdout)

sys.exit(0)
